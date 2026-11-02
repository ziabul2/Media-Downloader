"""Proxy stays off by default, and when enabled it still refuses private targets."""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.core.exceptions import APIError
from app.streaming.proxy import ProxyStreamer, filter_response_headers, iter_upstream, upstream_request_headers
from app.streaming.range_handler import forward_range


def test_range_header_is_strict() -> None:
    assert forward_range("bytes=0-10") == "bytes=0-10"
    assert forward_range("bytes=-10") == "bytes=-10"
    assert forward_range("bytes=0-") == "bytes=0-"
    assert forward_range("bytes=evil") is None
    assert forward_range("bytes=10-1") is None


def test_request_headers_drop_cookies() -> None:
    headers = upstream_request_headers(
        {"User-Agent": "ZIM", "Cookie": "session=nope", "Referer": "https://archive.org/"},
        "bytes=0-10",
    )
    assert "Cookie" not in headers
    assert headers["Range"] == "bytes=0-10"
    assert headers["Referer"] == "https://archive.org/"


def test_response_headers_drop_set_cookie() -> None:
    response = httpx.Response(
        200,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": "4",
            "Set-Cookie": "a=b",
            "Content-Disposition": "attachment; filename=\"evil\r\nX: y\"",
        },
    )
    filtered = filter_response_headers(response, "sample.mp4", "video/mp4")
    assert "set-cookie" not in {key.lower() for key in filtered}
    assert filtered["Content-Disposition"] == 'attachment; filename="sample.mp4"'
    assert filtered["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_stream_closes_upstream_when_cancelled() -> None:
    class Fake:
        def __init__(self) -> None:
            self.closed = False

        async def aiter_bytes(self):
            yield b"one"
            yield b"two"

        async def aclose(self) -> None:
            self.closed = True

    fake = Fake()
    generator = iter_upstream(fake, max_bytes=100, max_seconds=5)  # type: ignore[arg-type]
    assert await generator.__anext__() == b"one"
    await generator.aclose()
    assert fake.closed is True


@pytest.mark.asyncio
async def test_proxy_blocks_private_target() -> None:
    settings = Settings(proxy_enabled=True)
    streamer = ProxyStreamer()
    with pytest.raises(APIError) as caught:
        await streamer.open(
            url="http://127.0.0.1/secret",
            required_headers=None,
            range_header=None,
            settings=settings,
        )
    assert caught.value.code == "BLOCKED_DESTINATION"


@pytest.mark.asyncio
async def test_proxy_forwards_range_and_206() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["range"] == "bytes=0-4"
        return httpx.Response(
            206,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": "bytes 0-4/9",
                "Content-Length": "5",
                "Accept-Ranges": "bytes",
                "Set-Cookie": "nope=1",
            },
            content=b"hello",
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        streamer = ProxyStreamer(http_client)
        status, _headers, upstream, owned = await streamer.open(
            url="https://cdn.example.net/video.mp4",
            required_headers={"User-Agent": "ZIM"},
            range_header="bytes=0-4",
            settings=Settings(proxy_enabled=True),
            resolver=lambda host, port: __import__("ipaddress").ip_address("93.184.216.34")
            and [__import__("ipaddress").ip_address("93.184.216.34")],
        )
        assert owned is None
        assert status == 206
        chunks = []
        async for chunk in iter_upstream(upstream, max_bytes=100, max_seconds=5):
            chunks.append(chunk)
    assert b"".join(chunks) == b"hello"


@pytest.mark.asyncio
async def test_upstream_416() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(416, content=b"secret upstream html")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        streamer = ProxyStreamer(http_client)
        with pytest.raises(APIError) as caught:
            await streamer.open(
                url="https://cdn.example.net/video.mp4",
                required_headers=None,
                range_header="bytes=999-1000",
                settings=Settings(proxy_enabled=True),
                resolver=lambda host, port: [__import__("ipaddress").ip_address("93.184.216.34")],
            )
    assert caught.value.status_code == 416
    assert "secret" not in caught.value.message
