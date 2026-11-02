"""Stream an approved upstream file in chunks. The body is never buffered whole."""

from __future__ import annotations

import time
from typing import AsyncIterator

import httpx

from app.config import Settings
from app.core.exceptions import APIError
from app.core.url_validation import validate_url
from app.streaming.range_handler import content_disposition, forward_range, safe_content_type

_FORWARD_RESPONSE = {"content-type", "content-length", "content-range", "accept-ranges"}
_ALLOWED_REQUEST = {"user-agent", "referer", "origin", "accept"}


def upstream_request_headers(required: dict | None, range_header: str | None) -> dict[str, str]:
    outgoing: dict[str, str] = {}
    for key, value in (required or {}).items():
        if key.lower() in _ALLOWED_REQUEST and isinstance(value, str):
            if "\r" in value or "\n" in value:
                continue
            outgoing[key] = value
    parsed = forward_range(range_header)
    if parsed:
        outgoing["Range"] = parsed
    outgoing.setdefault("User-Agent", "ZIMMediaAPI/0.1")
    return outgoing


def filter_response_headers(upstream: httpx.Response, filename: str, fallback_type: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in upstream.headers.items():
        if key.lower() not in _FORWARD_RESPONSE:
            continue
        if "\r" in value or "\n" in value:
            continue
        if key.lower() == "content-type":
            headers["Content-Type"] = safe_content_type(value, fallback_type)
        else:
            headers[key] = value
    headers.setdefault("Content-Type", safe_content_type(None, fallback_type))
    headers["Content-Disposition"] = content_disposition(filename)
    headers["Cache-Control"] = "no-store"
    headers["Referrer-Policy"] = "no-referrer"
    headers["X-Content-Type-Options"] = "nosniff"
    return headers


async def iter_upstream(
    response: httpx.Response,
    *,
    max_bytes: int,
    max_seconds: int,
) -> AsyncIterator[bytes]:
    started = time.monotonic()
    sent = 0
    try:
        async for chunk in response.aiter_bytes():
            if time.monotonic() - started > max_seconds:
                raise APIError("UPSTREAM_ERROR", "The upstream stream exceeded its time limit.")
            sent += len(chunk)
            if sent > max_bytes:
                raise APIError("UPSTREAM_ERROR", "The upstream stream exceeded its size limit.")
            yield chunk
    finally:
        await response.aclose()


class ProxyStreamer:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def open(
        self,
        *,
        url: str,
        required_headers: dict | None,
        range_header: str | None,
        settings: Settings,
        resolver=None,
    ) -> tuple[int, dict[str, str], AsyncIterator[bytes], httpx.Response]:
        if not settings.proxy_enabled:
            raise APIError("PROXY_NOT_ALLOWED", "Proxy streaming is disabled.")
        validated = validate_url(url, resolver=resolver)
        headers = upstream_request_headers(required_headers, range_header)
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.proxy_connect_timeout_seconds,
                read=settings.proxy_read_timeout_seconds,
            ),
            follow_redirects=False,
            trust_env=False,
        )
        owned = self._client is None
        current = validated.url
        response: httpx.Response | None = None
        try:
            for _ in range(3):
                request = client.build_request("GET", current, headers=headers)
                response = await client.send(request, stream=True)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    await response.aclose()
                    if not location:
                        raise APIError("UPSTREAM_ERROR", "The upstream redirect was not usable.")
                    current = str(httpx.URL(current).join(location))
                    validate_url(current, resolver=resolver)
                    continue
                break
            else:
                raise APIError("UPSTREAM_ERROR", "The upstream redirected too many times.")
            assert response is not None
            if response.status_code == 416:
                await response.aclose()
                raise APIError("UPSTREAM_ERROR", "The requested byte range is not satisfiable.", status_code=416)
            if response.status_code in {401, 403}:
                await response.aclose()
                raise APIError(
                    "MEDIA_URL_EXPIRED",
                    "The source refused the media URL. Extract again. Access controls are not bypassed.",
                )
            if response.status_code == 410:
                await response.aclose()
                raise APIError("MEDIA_URL_EXPIRED", "The source URL has expired. Extract again.")
            if response.status_code not in {200, 206}:
                await response.aclose()
                raise APIError("UPSTREAM_ERROR", "The source did not return the media.")
            return response.status_code, dict(response.headers), response, client if owned else None  # type: ignore[return-value]
        except APIError:
            if owned:
                await client.aclose()
            raise
        except httpx.TimeoutException as exc:
            if owned:
                await client.aclose()
            raise APIError("UPSTREAM_ERROR", "The source timed out.", retryable=True) from exc
        except httpx.HTTPError as exc:
            if owned:
                await client.aclose()
            raise APIError("UPSTREAM_ERROR", "The source could not be reached.", retryable=True) from exc
