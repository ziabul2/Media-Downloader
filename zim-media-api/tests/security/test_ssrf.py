"""SSRF: private, loopback, metadata, and non-http schemes never pass."""

from __future__ import annotations

import ipaddress

import pytest

from app.core.exceptions import APIError
from app.core.url_validation import install_socket_guard, ip_is_blocked, remove_socket_guard, validate_url

PUBLIC = [ipaddress.ip_address("93.184.216.34")]


def _resolver(hostname: str, port: int):
    del port
    mapping = {
        "public.example": PUBLIC,
        "rebind.example": [ipaddress.ip_address("1.1.1.1"), ipaddress.ip_address("10.1.2.3")],
        "onlyprivate.example": [ipaddress.ip_address("192.168.1.20")],
        "metadata.example": [ipaddress.ip_address("169.254.169.254")],
    }
    if hostname not in mapping:
        raise APIError("INVALID_URL", "The hostname could not be resolved.")
    return mapping[hostname]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://public.example/a",
        "gopher://public.example/a",
        "javascript:alert(1)",
        "http://user:pass@public.example/a",
        "http://localhost/a",
        "http://127.0.0.1/a",
        "http://127.0.0.1:8080/a",
        "http://2130706433/a",
        "http://0x7f000001/a",
        "http://10.0.0.8/secret",
        "http://192.168.0.4/a",
        "http://172.16.0.4/a",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/a",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://onlyprivate.example/a",
        "http://rebind.example/a",
        "http://metadata.example/latest",
        "http://0.0.0.0/",
        "http://224.0.0.1/",
        "http://foo.local/a",
        "http://printer.internal/a",
    ],
)
def test_blocked_urls(url: str) -> None:
    with pytest.raises(APIError) as caught:
        validate_url(url, resolver=_resolver)
    assert caught.value.code in {"BLOCKED_DESTINATION", "UNSUPPORTED_SCHEME", "INVALID_URL"}


def test_public_url_is_normalized() -> None:
    validated = validate_url("HTTPS://Public.Example:443/watch?v=1", resolver=_resolver)
    assert validated.url == "https://public.example/watch?v=1"
    assert validated.ips == ("93.184.216.34",)


def test_multicast_and_cgnat_are_blocked() -> None:
    assert ip_is_blocked("224.0.0.1")
    assert ip_is_blocked("100.64.0.1")
    assert ip_is_blocked("8.8.8.8") is False


def test_socket_guard_blocks_loopback() -> None:
    import socket

    install_socket_guard()
    try:
        with pytest.raises(APIError) as caught:
            socket.create_connection(("127.0.0.1", 9), timeout=1)
        assert caught.value.code == "BLOCKED_DESTINATION"
    finally:
        remove_socket_guard()
