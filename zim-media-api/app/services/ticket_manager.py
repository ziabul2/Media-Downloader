"""Opaque download tickets. The public token is random and is not a signed URL."""

from __future__ import annotations

import time

from app.config import Settings
from app.core.exceptions import APIError
from app.core.security import generate_ticket
from app.services.store import Store


def _key(token: str) -> str:
    return f"ticket:{token}"


def create_ticket(store: Store, settings: Settings, record: dict) -> dict:
    token = generate_ticket()
    now = int(time.time())
    payload = {
        "ticket": token,
        "owner_key_id": record["owner_key_id"],
        "source_url": record["source_url"],
        "required_headers": record.get("required_headers") or {},
        "format_id": record["format_id"],
        "filename": record["filename"],
        "ext": record.get("ext"),
        "content_type": record.get("content_type"),
        "delivery": record["delivery"],
        "expose_url": bool(record.get("expose_url")),
        "created_at": now,
        "expires_at": now + settings.default_ticket_ttl_seconds,
        "uses": 0,
        "revoked": False,
        "extraction_id": record.get("extraction_id"),
        "constraints": record.get("constraints") or {},
    }
    store.set_json(_key(token), payload, settings.default_ticket_ttl_seconds)
    return payload


def get_ticket(store: Store, token: str, *, touch: bool = False, one_time: bool = False) -> dict:
    if not token or len(token) > 200:
        raise APIError("INVALID_TICKET", "The download ticket is not valid.")
    payload = store.get_json(_key(token))
    if not payload:
        raise APIError("INVALID_TICKET", "The download ticket is not valid.")
    now = int(time.time())
    if payload.get("revoked"):
        raise APIError("INVALID_TICKET", "The download ticket has been revoked.", status_code=403)
    if int(payload.get("expires_at") or 0) <= now:
        raise APIError("TICKET_EXPIRED", "The download ticket has expired.")
    if one_time and int(payload.get("uses") or 0) >= 1:
        raise APIError("INVALID_TICKET", "The download ticket was already used.")
    if touch:
        payload["uses"] = int(payload.get("uses") or 0) + 1
        remaining = max(1, int(payload["expires_at"]) - now)
        store.set_json(_key(token), payload, remaining)
    return payload


def revoke_ticket(store: Store, token: str, *, owner_key_id: str) -> dict:
    payload = get_ticket(store, token)
    if payload.get("owner_key_id") != owner_key_id:
        raise APIError("FORBIDDEN", "This ticket belongs to another API key.")
    payload["revoked"] = True
    remaining = max(1, int(payload["expires_at"]) - int(time.time()))
    store.set_json(_key(token), payload, remaining)
    return payload


def public_ticket(payload: dict, *, download_url: str) -> dict:
    now = int(time.time())
    data = {
        "ticket": payload["ticket"],
        "delivery": payload["delivery"],
        "download_url": download_url,
        "filename": payload["filename"],
        "format": payload.get("ext"),
        "expires_in": max(0, int(payload["expires_at"]) - now),
        "constraints": {
            "requires_non_browser_headers": bool(
                (payload.get("constraints") or {}).get("requires_non_browser_headers")
            ),
            "note": (payload.get("constraints") or {}).get("note"),
        },
    }
    if payload.get("expose_url") and payload.get("delivery") == "direct":
        data["url"] = payload["source_url"]
        headers = payload.get("required_headers") or None
        if headers:
            data["required_headers"] = headers
    if payload.get("delivery") == "proxy":
        data["stream_url"] = download_url.replace("/download/", "/stream/")
    return data
