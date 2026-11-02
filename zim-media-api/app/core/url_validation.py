"""SSRF controls for every user-supplied URL and every outbound connection.

A hostname is never trusted just because one lookup looked public. Literal
private addresses, cloud metadata names, and non-global DNS answers are
rejected. Callers that follow redirects must run each hop through
``validate_url`` again.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from app.core.exceptions import APIError

Resolver = Callable[[str, int], list[ipaddress.IPv4Address | ipaddress.IPv6Address]]

_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "instance-data.ec2.internal",
}
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".intranet", ".localdomain")
_INTEGER_IP = re.compile(r"\d{1,10}")
_HEX_IP = re.compile(r"0x[0-9a-fA-F]{1,8}")


@dataclass(frozen=True)
class ValidatedURL:
    url: str
    hostname: str
    port: int
    ips: tuple[str, ...]


def ip_is_blocked(value: ipaddress.IPv4Address | ipaddress.IPv6Address | str) -> bool:
    ip = ipaddress.ip_address(value) if isinstance(value, str) else value
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if (
        ip.is_multicast
        or ip.is_unspecified
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or not ip.is_global
    ):
        return True
    return False


def coerce_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    text = host.strip().strip("[]")
    if not text:
        return None
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        pass
    if _INTEGER_IP.fullmatch(text):
        number = int(text)
        if 0 <= number <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(number)
    if _HEX_IP.fullmatch(text):
        number = int(text, 16)
        if 0 <= number <= 0xFFFFFFFF:
            return ipaddress.IPv4Address(number)
    return None


def hostname_is_blocked(hostname: str) -> bool:
    host = hostname.strip(".").lower()
    if host in _BLOCKED_HOSTS:
        return True
    return any(host.endswith(suffix) for suffix in _BLOCKED_SUFFIXES)


def default_resolver(hostname: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise APIError("INVALID_URL", "The hostname could not be resolved.") from exc
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        address = info[4][0]
        try:
            ips.append(ipaddress.ip_address(address))
        except ValueError:
            continue
    if not ips:
        raise APIError("INVALID_URL", "The hostname could not be resolved.")
    return ips


def validate_url(
    raw: str,
    *,
    resolver: Resolver | None = None,
    max_length: int = 2048,
) -> ValidatedURL:
    if raw is None or not isinstance(raw, str):
        raise APIError("INVALID_URL", "A URL is required.")
    candidate = raw.strip()
    if not candidate or len(candidate) > max_length:
        raise APIError("INVALID_URL", "The URL is empty or too long.")
    if any(char in candidate for char in ("\r", "\n", "\t", "\\", " ")):
        raise APIError("INVALID_URL", "The URL contains characters that are not allowed.")

    parts = urlsplit(candidate)
    scheme = (parts.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise APIError(
            "UNSUPPORTED_SCHEME",
            "Only http and https URLs are accepted.",
        )
    if parts.username is not None or parts.password is not None:
        raise APIError("INVALID_URL", "URLs with embedded credentials are not accepted.")
    if not parts.hostname:
        raise APIError("INVALID_URL", "The URL has no hostname.")

    hostname = parts.hostname.strip(".").lower()
    if hostname_is_blocked(hostname):
        raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")

    port = parts.port or (443 if scheme == "https" else 80)
    if port < 1 or port > 65535:
        raise APIError("INVALID_URL", "The URL port is not valid.")

    literal = coerce_ip(hostname)
    if literal is not None:
        if ip_is_blocked(literal):
            raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")
        ips = (str(literal),)
    else:
        lookup = resolver or default_resolver
        try:
            resolved = lookup(hostname, port)
        except APIError:
            raise
        except Exception as exc:
            raise APIError("INVALID_URL", "The hostname could not be resolved.") from exc
        if not resolved:
            raise APIError("INVALID_URL", "The hostname could not be resolved.")
        blocked = [str(ip) for ip in resolved if ip_is_blocked(ip)]
        if blocked or not any(not ip_is_blocked(ip) for ip in resolved):
            raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")
        # Mixed answers are rejected so a public record cannot launder a private one.
        if any(ip_is_blocked(ip) for ip in resolved):
            raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")
        ips = tuple(str(ip) for ip in resolved)

    host_for_url = f"[{hostname}]" if ":" in hostname and literal is not None else hostname
    default_port = 443 if scheme == "https" else 80
    if parts.port is None or parts.port == default_port:
        netloc = host_for_url
    else:
        netloc = f"{host_for_url}:{parts.port}"
    path = parts.path or ""
    query = f"?{parts.query}" if parts.query else ""
    normalized = f"{scheme}://{netloc}{path}{query}"
    return ValidatedURL(url=normalized, hostname=hostname, port=port, ips=ips)


def install_socket_guard() -> None:
    """Reject non-global destinations inside an extractor process."""

    if getattr(socket, "_zim_guard_installed", False):
        return

    real_getaddrinfo = socket.getaddrinfo
    real_create_connection = socket.create_connection

    def guarded_getaddrinfo(host, port, *args, **kwargs):  # type: ignore[no-untyped-def]
        results = real_getaddrinfo(host, port, *args, **kwargs)
        if host is None:
            return results
        literal = coerce_ip(str(host))
        if literal is not None and ip_is_blocked(literal):
            raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")
        if hostname_is_blocked(str(host)):
            raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")
        safe = []
        for item in results:
            address = item[4][0]
            try:
                parsed = ipaddress.ip_address(address)
            except ValueError:
                continue
            if not ip_is_blocked(parsed):
                safe.append(item)
        if not safe:
            raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")
        return safe

    def guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = address[0] if isinstance(address, tuple) else address
        literal = coerce_ip(str(host))
        if literal is not None and ip_is_blocked(literal):
            raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")
        if hostname_is_blocked(str(host)):
            raise APIError("BLOCKED_DESTINATION", "That destination is blocked.")
        return real_create_connection(address, *args, **kwargs)

    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]
    socket.create_connection = guarded_create_connection  # type: ignore[assignment]
    socket._zim_guard_installed = True  # type: ignore[attr-defined]
    socket._zim_real_getaddrinfo = real_getaddrinfo  # type: ignore[attr-defined]
    socket._zim_real_create_connection = real_create_connection  # type: ignore[attr-defined]


def remove_socket_guard() -> None:
    if not getattr(socket, "_zim_guard_installed", False):
        return
    socket.getaddrinfo = socket._zim_real_getaddrinfo  # type: ignore[attr-defined]
    socket.create_connection = socket._zim_real_create_connection  # type: ignore[attr-defined]
    socket._zim_guard_installed = False  # type: ignore[attr-defined]
