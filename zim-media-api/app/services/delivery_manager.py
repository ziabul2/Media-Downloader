"""Pick direct, redirect, or a permitted proxy. Never claim a mode the source cannot support."""

from __future__ import annotations

from app.config import Settings
from app.core.exceptions import APIError
from app.core.url_validation import validate_url

_DIRECT_PROTOCOLS = {"http", "https"}
_SOFT_HEADERS = {"user-agent", "accept", "accept-language"}


def special_headers(headers: dict | None) -> dict:
    if not headers:
        return {}
    special = {}
    for key, value in headers.items():
        if key.lower() not in _SOFT_HEADERS:
            special[key] = value
    return special


def assess_delivery(fmt: dict, preference: str, settings: Settings, resolver=None) -> dict:
    if fmt.get("requires_merge"):
        raise APIError(
            "DELIVERY_UNAVAILABLE",
            "This format is video-only or split from its audio. "
            "Server-side merging is disabled. Choose a progressive file or merge the streams on the client.",
        )
    if fmt.get("conversion_required"):
        raise APIError(
            "DELIVERY_UNAVAILABLE",
            "The requested container needs a conversion this server does not perform.",
        )
    protocol = fmt.get("protocol")
    url = fmt.get("url")
    if not url or protocol not in _DIRECT_PROTOCOLS:
        if preference == "proxy" or (preference == "auto" and settings.proxy_enabled):
            raise APIError(
                "DELIVERY_UNAVAILABLE",
                "This format is not a single HTTP file. Playlist and adaptive streams are not proxied as a download.",
            )
        raise APIError(
            "DELIVERY_UNAVAILABLE",
            "This format has no directly usable HTTP file URL. ZIM will not pretend otherwise.",
        )

    # Re-check the media URL itself. A public page can still point at a blocked host.
    validate_url(url, resolver=resolver)
    headers = fmt.get("http_headers") or {}
    constrained = special_headers(headers)
    constraints = {
        "requires_non_browser_headers": bool(constrained),
        "headers": headers or None,
        "note": None,
    }
    if constrained:
        constraints["note"] = (
            "The source URL is tied to extra headers. A plain browser navigation may fail. "
            "Those headers are returned only to the authenticated client and are not logged."
        )

    if preference == "proxy":
        if not settings.proxy_enabled:
            raise APIError(
                "PROXY_NOT_ALLOWED",
                "Proxy streaming is disabled. Use direct or redirect delivery.",
            )
        return {"delivery": "proxy", "expose_url": False, "constraints": constraints}

    if preference == "redirect":
        if constrained:
            constraints["note"] = (
                "Redirect delivery cannot attach the source's required headers. "
                "Direct delivery was kept available in this ticket's info, but the redirect itself may fail."
            )
        return {"delivery": "redirect", "expose_url": False, "constraints": constraints}

    # auto and direct both prefer a direct URL. Redirect remains available on the ticket.
    return {"delivery": "direct", "expose_url": True, "constraints": constraints}
