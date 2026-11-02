"""Tickets expire, revoke, and do not embed the media URL in the token."""

from __future__ import annotations

import time

import pytest

from app.config import Settings
from app.core.exceptions import APIError
from app.services.store import MemoryStore
from app.services.ticket_manager import create_ticket, get_ticket, public_ticket, revoke_ticket


def test_ticket_roundtrip_hides_url_until_direct() -> None:
    settings = Settings(default_ticket_ttl_seconds=900, dev_api_key="x")
    store = MemoryStore()
    payload = create_ticket(
        store,
        settings,
        {
            "owner_key_id": "key_1",
            "source_url": "https://cdn.example.net/video.mp4?signature=sekret",
            "required_headers": {},
            "format_id": "22",
            "filename": "sample.mp4",
            "ext": "mp4",
            "delivery": "redirect",
            "expose_url": False,
        },
    )
    assert "cdn.example" not in payload["ticket"]
    assert "sekret" not in payload["ticket"]
    view = public_ticket(payload, download_url="/api/v1/download/" + payload["ticket"])
    assert "url" not in view
    loaded = get_ticket(store, payload["ticket"])
    assert loaded["source_url"].startswith("https://cdn.example.net/")


def test_expired_ticket() -> None:
    settings = Settings(default_ticket_ttl_seconds=900)
    store = MemoryStore()
    payload = create_ticket(
        store,
        settings,
        {
            "owner_key_id": "key_1",
            "source_url": "https://cdn.example.net/video.mp4",
            "format_id": "22",
            "filename": "sample.mp4",
            "ext": "mp4",
            "delivery": "direct",
            "expose_url": True,
        },
    )
    payload["expires_at"] = int(time.time()) - 5
    store.set_json(f"ticket:{payload['ticket']}", payload, 30)
    with pytest.raises(APIError) as caught:
        get_ticket(store, payload["ticket"])
    assert caught.value.code == "TICKET_EXPIRED"


def test_revoked_ticket() -> None:
    settings = Settings(default_ticket_ttl_seconds=900)
    store = MemoryStore()
    payload = create_ticket(
        store,
        settings,
        {
            "owner_key_id": "key_1",
            "source_url": "https://cdn.example.net/video.mp4",
            "format_id": "22",
            "filename": "sample.mp4",
            "ext": "mp4",
            "delivery": "redirect",
            "expose_url": False,
        },
    )
    revoke_ticket(store, payload["ticket"], owner_key_id="key_1")
    with pytest.raises(APIError) as caught:
        get_ticket(store, payload["ticket"])
    assert caught.value.status_code == 403
