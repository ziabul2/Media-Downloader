"""Run extraction out of process, then cache the normalized result."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time

from app.config import Settings
from app.core.exceptions import APIError
from app.core.security import generate_ticket
from app.core.url_validation import validate_url
from app.services.format_selector import select_formats
from app.services.store import Store


def public_extraction(record: dict) -> dict:
    return {
        "extraction_id": record["extraction_id"],
        "platform": record.get("platform"),
        "title": record.get("title"),
        "duration": record.get("duration"),
        "thumbnail": record.get("thumbnail"),
        "is_live": record.get("is_live", False),
        "formats": record.get("public_formats") or [],
        "selection": record.get("selection"),
    }


async def run_local_extractor(url: str, settings: Settings) -> dict:
    payload = json.dumps(
        {
            "url": url,
            "prefixes": settings.extractor_prefixes(),
            "allow_generic": settings.allow_generic_extractor,
            "socket_timeout": settings.extraction_socket_timeout_seconds,
        }
    ).encode("utf-8")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app.extractors.job",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(
            proc.communicate(payload),
            timeout=settings.extraction_timeout_seconds,
        )
    except (TimeoutError, asyncio.TimeoutError):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        raise APIError(
            "EXTRACTION_TIMEOUT",
            "Extraction took too long and was stopped.",
            retryable=True,
        )
    text = stdout.decode("utf-8", errors="replace").strip()
    if not text:
        raise APIError("EXTRACTION_FAILED", "Extraction failed.")
    if len(text) > 2_000_000:
        raise APIError("EXTRACTION_FAILED", "Extraction returned more data than allowed.")
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise APIError("EXTRACTION_FAILED", "Extraction failed.") from exc
    if not body.get("ok"):
        raise APIError(
            body.get("code") or "EXTRACTION_FAILED",
            body.get("message") or "Extraction failed.",
            retryable=bool(body.get("retryable")),
        )
    data = body.get("data")
    if not isinstance(data, dict):
        raise APIError("EXTRACTION_FAILED", "Extraction failed.")
    return data


async def run_queue_extractor(url: str, settings: Settings, store: Store) -> dict:
    if store.backend != "redis":  # type: ignore[attr-defined]
        raise APIError(
            "EXTRACTION_FAILED",
            "Queue extraction requires Redis. It was not silently run inside the API process.",
        )
    job_id = "job_" + generate_ticket()
    request = {
        "id": job_id,
        "url": url,
        "prefixes": settings.extractor_prefixes(),
        "allow_generic": settings.allow_generic_extractor,
        "socket_timeout": settings.extraction_socket_timeout_seconds,
    }
    # The worker list key is a Redis list. Memory store cannot host the queue.
    client = store._client  # type: ignore[attr-defined]
    client.lpush("zim:jobs", json.dumps(request))
    deadline = time.monotonic() + settings.extraction_timeout_seconds
    while time.monotonic() < deadline:
        raw = client.get(f"zim:job:{job_id}")
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            body = json.loads(raw)
            client.delete(f"zim:job:{job_id}")
            if not body.get("ok"):
                raise APIError(
                    body.get("code") or "EXTRACTION_FAILED",
                    body.get("message") or "Extraction failed.",
                    retryable=bool(body.get("retryable")),
                )
            return body["data"]
        await asyncio.sleep(0.25)
    raise APIError("EXTRACTION_TIMEOUT", "Extraction took too long and was stopped.", retryable=True)


class ExtractionService:
    def __init__(self, runner=None) -> None:
        self.runner = runner

    async def extract(
        self,
        *,
        url: str,
        media_type: str,
        preferred_format: str,
        preferred_quality: str | None,
        settings: Settings,
        store: Store,
        slots: asyncio.Semaphore,
        resolver=None,
    ) -> dict:
        validated = validate_url(url, resolver=resolver, max_length=settings.max_url_length)
        acquired = False
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.05)
            acquired = True
        except TimeoutError as exc:
            raise APIError(
                "RATE_LIMIT_EXCEEDED",
                "Too many extractions are already running.",
                retryable=True,
            ) from exc
        try:
            if self.runner is not None:
                info = await self.runner(validated.url, settings)
            elif settings.extraction_backend == "queue":
                info = await run_queue_extractor(validated.url, settings, store)
            else:
                info = await run_local_extractor(validated.url, settings)
        finally:
            if acquired:
                slots.release()

        if info.get("is_live"):
            for fmt in info.get("formats") or []:
                fmt["delivery_compatible"] = False
                fmt["note"] = "Live streams are not offered as a file download."
        chosen = select_formats(
            info.get("formats") or [],
            preferred_format=preferred_format,
            preferred_quality=preferred_quality,
            media_type=media_type,
        )
        extraction_id = "ext_" + generate_ticket()[:16]
        record = {
            "extraction_id": extraction_id,
            "source_url": validated.url,
            "platform": info.get("platform"),
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "is_live": info.get("is_live", False),
            "public_formats": chosen["formats"],
            "formats": chosen["internal_formats"],
            "selection": chosen["selection"],
            "created_at": int(time.time()),
        }
        store.set_json(f"extract:{extraction_id}", record, settings.metadata_cache_ttl_seconds)
        return public_extraction(record)


def load_extraction(store: Store, extraction_id: str) -> dict:
    record = store.get_json(f"extract:{extraction_id}")
    if not record:
        raise APIError("FORMAT_UNAVAILABLE", "The extraction expired or does not exist. Extract again.")
    return record
