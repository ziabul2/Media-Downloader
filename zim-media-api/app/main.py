"""FastAPI gateway. Extraction, tickets, and delivery live in services."""

from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import developer, download, extract, formats, health, stream
from app.config import Settings, load_settings
from app.core.exceptions import APIError
from app.core.logging import configure_logging
from app.core.metrics import Metrics
from app.core.redaction import redact
from app.core.security import hash_api_key
from app.database.models import Base
from app.database.repositories import (
    ensure_default_plan,
    ensure_developer,
    get_key_by_hash,
    insert_key,
    record_usage,
)
from app.database.session import make_engine, make_session_factory
from app.schemas.response import fail
from app.services.extraction import ExtractionService
from app.services.store import build_store

logger = logging.getLogger("zim")
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _dev_key(settings: Settings) -> str:
    if settings.dev_api_key:
        return settings.dev_api_key
    path = Path(settings.data_dir) / "dev_api_key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    from app.core.security import generate_api_key

    generated = generate_api_key()
    path.write_text(generated, encoding="utf-8")
    path.chmod(0o600)
    return generated


def _seed(app: FastAPI) -> None:
    settings: Settings = app.state.settings
    if settings.auto_create_schema:
        Base.metadata.create_all(app.state.engine)
    db = app.state.session_factory()
    try:
        ensure_default_plan(db, settings)
        if settings.app_env == "development":
            plaintext = _dev_key(settings)
            app.state.dev_api_key = plaintext
            developer = ensure_developer(db, name="Local console", email=None)
            digest = hash_api_key(plaintext, settings.api_key_pepper)
            if get_key_by_hash(db, digest) is None:
                from app.core.security import key_prefix

                insert_key(
                    db,
                    developer_id=developer.id,
                    key_hash=digest,
                    key_prefix=key_prefix(plaintext),
                    role="admin",
                )
        else:
            app.state.dev_api_key = None
    finally:
        db.close()


def create_app(
    settings: Settings | None = None,
    *,
    store=None,
    runner=None,
    resolver=None,
) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        _seed(app)
        if settings.api_key_pepper == "dev-pepper-change-me" and settings.app_env != "production":
            logger.warning("using_development_api_key_pepper")
        if not settings.proxy_enabled:
            logger.info("proxy_streaming_disabled")
        yield
        app.state.engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Extract public media metadata and hand the device a direct or redirect "
            "download from the original host. ZIM does not keep the media."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings
    app.state.store = store or build_store(settings.redis_url, required=settings.redis_required)
    app.state.engine = make_engine(settings.database_url)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.metrics = Metrics()
    app.state.extraction = ExtractionService(runner=runner)
    app.state.resolver = resolver
    import asyncio

    app.state.extract_slots = asyncio.Semaphore(settings.max_concurrent_extractions)
    app.state.stream_slots = asyncio.Semaphore(settings.max_concurrent_streams)
    app.state.proxy_client = None

    if settings.cors_origin_list():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list(),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-API-Key"],
            allow_credentials=False,
        )

    @app.middleware("http")
    async def guard_and_log(request: Request, call_next):
        request_id = "req_" + secrets.token_hex(8)
        request.state.request_id = request_id
        request.state.delivery = None
        request.state.principal = None
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > settings.max_body_bytes:
                    return JSONResponse(
                        fail("INVALID_REQUEST", "The request body is too large.", request_id),
                        status_code=413,
                    )
            except ValueError:
                return JSONResponse(
                    fail("INVALID_REQUEST", "The request body is not valid.", request_id),
                    status_code=400,
                )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.error("unhandled_error")
            response = JSONResponse(
                fail("INTERNAL_ERROR", "The request failed.", request_id),
                status_code=500,
            )
        duration_ms = int((time.perf_counter() - started) * 1000)
        path = redact(request.url.path)
        response.headers["X-Request-Id"] = request_id
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "endpoint": path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        principal = getattr(request.state, "principal", None)
        if principal is not None and principal.id != "anon" and path.startswith(settings.api_prefix):
            try:
                db = app.state.session_factory()
                try:
                    record_usage(
                        db,
                        developer_id=principal.developer_id,
                        api_key_id=principal.id,
                        endpoint=path,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        delivery_method=getattr(request.state, "delivery", None),
                    )
                finally:
                    db.close()
            except Exception:
                logger.warning("usage_write_failed")
        app.state.metrics.inc(
            "zim_requests_total",
            endpoint=_metric_endpoint(path, settings.api_prefix),
            status=str(response.status_code),
            delivery=str(getattr(request.state, "delivery", None) or "none"),
        )
        return response

    @app.exception_handler(APIError)
    async def on_api_error(request: Request, exc: APIError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "req_unknown")
        return JSONResponse(
            fail(exc.code, exc.message, request_id, exc.retryable),
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        del exc
        request_id = getattr(request.state, "request_id", "req_unknown")
        return JSONResponse(
            fail("INVALID_REQUEST", "The request body is not valid.", request_id),
            status_code=400,
        )

    app.include_router(health.router)
    prefix = settings.api_prefix
    app.include_router(health.router, prefix=prefix)
    app.include_router(extract.router, prefix=prefix)
    app.include_router(formats.router, prefix=prefix)
    app.include_router(download.router, prefix=prefix)
    app.include_router(stream.router, prefix=prefix)
    app.include_router(developer.router, prefix=prefix)

    @app.get("/metrics")
    def metrics() -> JSONResponse:
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(app.state.metrics.render(), media_type="text/plain; version=0.0.4")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def console() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


def _metric_endpoint(path: str, prefix: str) -> str:
    if path.startswith(f"{prefix}/download"):
        return f"{prefix}/download"
    if path.startswith(f"{prefix}/stream"):
        return f"{prefix}/stream"
    if path.startswith(f"{prefix}/extract"):
        return f"{prefix}/extract"
    if path.startswith(f"{prefix}/formats"):
        return f"{prefix}/formats"
    if path.startswith(f"{prefix}/developer"):
        return f"{prefix}/developer"
    if path in {"/health", "/ready", "/version", "/metrics"} or path.startswith(prefix):
        return path.split("?")[0][:80]
    return "other"


app = create_app()
