"""Proxy fallback. Refuses to run unless the deployment explicitly enables it."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.exceptions import APIError
from app.services.ticket_manager import get_ticket
from app.streaming.proxy import ProxyStreamer, filter_response_headers, iter_upstream

router = APIRouter()


@router.get("/stream/{ticket}")
async def stream(ticket: str, request: Request):
    settings = request.app.state.settings
    if not settings.proxy_enabled:
        raise APIError(
            "PROXY_NOT_ALLOWED",
            "Proxy streaming is disabled. Use direct or redirect delivery.",
        )
    payload = get_ticket(
        request.app.state.store,
        ticket,
        touch=True,
        one_time=settings.ticket_one_time,
    )
    if payload.get("delivery") != "proxy":
        raise APIError("DELIVERY_UNAVAILABLE", "This ticket is not approved for proxy streaming.")
    request.state.delivery = "proxy"

    try:
        await asyncio.wait_for(request.app.state.stream_slots.acquire(), timeout=0.05)
    except TimeoutError as exc:
        raise APIError(
            "RATE_LIMIT_EXCEEDED",
            "Too many proxy streams are already running.",
            retryable=True,
        ) from exc

    streamer = ProxyStreamer(getattr(request.app.state, "proxy_client", None))
    try:
        status, raw_headers, upstream, owned_client = await streamer.open(
            url=payload["source_url"],
            required_headers=payload.get("required_headers"),
            range_header=request.headers.get("range"),
            settings=settings,
            resolver=request.app.state.resolver,
        )
    except Exception:
        request.app.state.stream_slots.release()
        raise

    class _HeaderView:
        def __init__(self, headers: dict) -> None:
            self.headers = headers

    filtered = filter_response_headers(
        _HeaderView(raw_headers),  # type: ignore[arg-type]
        payload.get("filename") or "download.bin",
        payload.get("content_type") or "application/octet-stream",
    )

    async def body():
        try:
            async for chunk in iter_upstream(
                upstream,
                max_bytes=settings.max_proxy_bytes,
                max_seconds=settings.max_proxy_duration_seconds,
            ):
                yield chunk
        finally:
            if owned_client is not None:
                await owned_client.aclose()
            request.app.state.stream_slots.release()

    media_status = 206 if status == 206 else 200
    return StreamingResponse(body(), status_code=media_status, headers=filtered)
