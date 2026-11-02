"""Liveness, readiness, version, platforms, and capabilities."""

from __future__ import annotations

import importlib.metadata
import sys

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.exceptions import APIError
from app.extractors.registry import supported_platforms
from app.schemas.response import ok

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return ok({"status": "ok"})


@router.get("/ready")
def ready(request: Request) -> dict:
    settings = request.app.state.settings
    checks = {"database": False, "redis": None}
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        raise APIError("INTERNAL_ERROR", "The database is not ready.") from exc
    store = request.app.state.store
    if settings.redis_required:
        checks["redis"] = getattr(store, "backend", "") == "redis"
        if not checks["redis"]:
            raise APIError("INTERNAL_ERROR", "Redis is not ready.")
    else:
        checks["redis"] = getattr(store, "backend", "memory") == "redis"
    if not checks["database"]:
        raise APIError("INTERNAL_ERROR", "The database is not ready.")
    return ok({"status": "ready", "checks": checks})


@router.get("/version")
def version(request: Request) -> dict:
    try:
        extractor_version = importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        extractor_version = "unknown"
    settings = request.app.state.settings
    return ok(
        {
            "api": settings.app_version,
            "name": settings.app_name,
            "python": sys.version.split()[0],
            "yt_dlp": extractor_version,
            "environment": settings.app_env,
        }
    )


@router.get("/platforms")
def platforms(request: Request) -> dict:
    settings = request.app.state.settings
    return ok(
        {
            "platforms": supported_platforms(settings.extractor_prefixes()),
            "generic_extractor": settings.allow_generic_extractor,
        }
    )


@router.get("/capabilities")
def capabilities(request: Request) -> dict:
    settings = request.app.state.settings
    return ok(
        {
            "formats": ["mp4", "m4a", "mp3", "original"],
            "delivery_methods": ["direct", "redirect"] + (["proxy"] if settings.proxy_enabled else []),
            "proxy_enabled": settings.proxy_enabled,
            "server_side_merge": settings.ffmpeg_merge_enabled,
            "server_side_mp3_conversion": settings.ffmpeg_convert_enabled,
            "notes": [
                "Direct delivery is preferred. Media bytes are not stored on this server.",
                "MP3 is reported only when the source actually provides MP3.",
                "Separate audio and video streams are labeled requires_merge and are not merged here.",
                "Proxy streaming is off unless PROXY_ENABLED=true.",
            ],
        }
    )
