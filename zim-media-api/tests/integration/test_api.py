"""API contract: health, extraction, direct and redirect delivery, quotas, keys."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.exceptions import APIError
from app.main import create_app
from app.services.extraction import run_local_extractor

SAMPLE = "https://archive.org/details/BigBuckBunny_124"


def test_health_ready_version_platforms(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["success"] is True
    assert health.json()["data"]["status"] == "ok"
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["data"]["checks"]["database"] is True
    version = client.get("/version")
    assert version.json()["data"]["yt_dlp"]
    platforms = client.get("/platforms")
    ids = [item["id"] for item in platforms.json()["data"]["platforms"]]
    assert "youtube" in ids
    caps = client.get("/api/v1/capabilities")
    assert caps.json()["data"]["proxy_enabled"] is False
    assert "mp3" in caps.json()["data"]["formats"]


def test_auth_required(client: TestClient) -> None:
    response = client.post("/api/v1/extract", json={"url": SAMPLE})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_extract_and_direct_delivery(client: TestClient, auth: dict) -> None:
    response = client.post(
        "/api/v1/extract",
        headers=auth,
        json={
            "url": SAMPLE,
            "media_type": "video",
            "preferred_format": "mp4",
            "preferred_quality": "1080p",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["title"] == "Licensed Sample"
    assert data["selection"]["substituted"] is True
    assert data["selection"]["recommended_format_id"] == "progressive"
    formats = {item["format_id"]: item for item in data["formats"]}
    assert "url" not in formats["progressive"]
    assert formats["video1080"]["requires_merge"] is True
    assert formats["video1080"]["has_audio"] is False

    link = client.post(
        "/api/v1/download-link",
        headers=auth,
        json={
            "extraction_id": data["extraction_id"],
            "format_id": "progressive",
            "delivery": "auto",
        },
    )
    assert link.status_code == 200
    ticket = link.json()["data"]
    assert ticket["delivery"] == "direct"
    assert ticket["url"] == "https://cdn.example.net/video.mp4"
    assert ticket["filename"].endswith(".mp4")
    assert "signature" not in ticket["url"]

    redirect = client.post(
        "/api/v1/download-link",
        headers=auth,
        json={
            "extraction_id": data["extraction_id"],
            "format_id": "progressive",
            "delivery": "redirect",
        },
    )
    redirect_body = redirect.json()["data"]
    assert "url" not in redirect_body
    follow = client.get(redirect_body["download_url"], follow_redirects=False)
    assert follow.status_code == 302
    assert follow.headers["location"] == "https://cdn.example.net/video.mp4"
    assert follow.headers["cache-control"] == "no-store"
    assert follow.headers["referrer-policy"] == "no-referrer"


def test_split_stream_is_not_delivered_as_a_file(client: TestClient, auth: dict) -> None:
    extracted = client.post(
        "/api/v1/extract",
        headers=auth,
        json={"url": SAMPLE, "preferred_format": "original", "preferred_quality": "best"},
    ).json()["data"]
    refused = client.post(
        "/api/v1/download-link",
        headers=auth,
        json={"extraction_id": extracted["extraction_id"], "format_id": "video1080", "delivery": "direct"},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "DELIVERY_UNAVAILABLE"


def test_m4a_download(client: TestClient, auth: dict) -> None:
    extracted = client.post(
        "/api/v1/extract",
        headers=auth,
        json={"url": SAMPLE, "media_type": "audio", "preferred_format": "m4a"},
    ).json()["data"]
    assert extracted["selection"]["actual_ext"] == "m4a"
    link = client.post(
        "/api/v1/download-link",
        headers=auth,
        json={
            "extraction_id": extracted["extraction_id"],
            "format_id": extracted["selection"]["recommended_format_id"],
            "delivery": "direct",
        },
    )
    assert link.status_code == 200
    assert link.json()["data"]["format"] == "m4a"
    assert link.json()["data"]["url"].endswith(".m4a")


def test_blocked_destination_does_not_extract(client: TestClient, auth: dict) -> None:
    response = client.post(
        "/api/v1/extract",
        headers=auth,
        json={"url": "http://127.0.0.1/secret"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BLOCKED_DESTINATION"


def test_unsupported_scheme(client: TestClient, auth: dict) -> None:
    response = client.post("/api/v1/extract", headers=auth, json={"url": "file:///etc/passwd"})
    assert response.json()["error"]["code"] in {"UNSUPPORTED_SCHEME", "INVALID_URL", "INVALID_REQUEST"}


def test_expired_and_revoked_ticket(client: TestClient, auth: dict) -> None:
    extracted = client.post(
        "/api/v1/extract",
        headers=auth,
        json={"url": SAMPLE, "preferred_format": "mp4", "preferred_quality": "720p"},
    ).json()["data"]
    created = client.post(
        "/api/v1/download-link",
        headers=auth,
        json={"extraction_id": extracted["extraction_id"], "format_id": "progressive", "delivery": "redirect"},
    ).json()["data"]
    info = client.get(f"/api/v1/download/{created['ticket']}/info", headers=auth)
    assert info.status_code == 200
    assert "url" not in info.json()["data"]
    assert "cdn.example" not in info.text

    deleted = client.delete(f"/api/v1/download/{created['ticket']}", headers=auth)
    assert deleted.status_code == 200
    denied = client.get(created["download_url"], follow_redirects=False)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "INVALID_TICKET"

    second = client.post(
        "/api/v1/download-link",
        headers=auth,
        json={"extraction_id": extracted["extraction_id"], "format_id": "progressive", "delivery": "redirect"},
    ).json()["data"]
    stored = client.app.state.store.get_json(f"ticket:{second['ticket']}")
    stored["expires_at"] = int(time.time()) - 10
    client.app.state.store.set_json(f"ticket:{second['ticket']}", stored, 60)
    expired = client.get(second["download_url"], follow_redirects=False)
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "TICKET_EXPIRED"


def test_invalid_ticket(client: TestClient) -> None:
    response = client.get("/api/v1/download/not-a-real-ticket", follow_redirects=False)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INVALID_TICKET"


def test_proxy_disabled(client: TestClient, auth: dict) -> None:
    extracted = client.post(
        "/api/v1/extract",
        headers=auth,
        json={"url": SAMPLE, "preferred_format": "mp4"},
    ).json()["data"]
    refused = client.post(
        "/api/v1/download-link",
        headers=auth,
        json={"extraction_id": extracted["extraction_id"], "format_id": "progressive", "delivery": "proxy"},
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "PROXY_NOT_ALLOWED"
    missing = client.get("/api/v1/stream/whatever")
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "PROXY_NOT_ALLOWED"


def test_rate_limit(settings: Settings, auth: dict) -> None:
    settings.requests_per_minute = 2
    application = create_app(settings, runner=_runner(), resolver=_resolver())
    with TestClient(application) as test_client:
        statuses = [
            test_client.post("/api/v1/extract", headers=auth, json={"url": SAMPLE}).status_code
            for _ in range(3)
        ]
    assert statuses[:2] == [200, 200]
    assert statuses[2] == 429


def test_key_is_hashed_and_rotation_hides_plaintext(client: TestClient, auth: dict, api_key: str) -> None:
    created = client.post("/api/v1/developer/keys", headers=auth, json={})
    assert created.status_code == 200
    plaintext = created.json()["data"]["api_key"]
    assert plaintext.startswith("zim_")
    listed = client.get("/api/v1/developer/keys", headers=auth)
    blob = listed.text
    assert plaintext not in blob
    assert api_key not in blob
    from app.core.security import hash_api_key

    stored = client.app.state.session_factory()
    try:
        from sqlalchemy import select
        from app.database.models import ApiKey

        rows = list(stored.scalars(select(ApiKey)).all())
    finally:
        stored.close()
    assert plaintext not in {row.key_hash for row in rows}
    assert hash_api_key(plaintext, "test-pepper") in {row.key_hash for row in rows}


def test_no_media_files_written(client: TestClient, auth: dict, settings: Settings) -> None:
    client.post("/api/v1/extract", headers=auth, json={"url": SAMPLE, "preferred_format": "mp4"})
    root = Path(settings.data_dir)
    media = list(root.rglob("*.mp4")) + list(root.rglob("*.m4a")) + list(root.rglob("*.webm"))
    assert media == []


def test_queue_backend_without_redis_does_not_fake_success(settings: Settings) -> None:
    settings.extraction_backend = "queue"

    async def unused(url: str, settings_obj: Settings):
        raise AssertionError("queue mode must not call the local runner")

    application = create_app(settings, runner=None, resolver=_resolver())
    application.state.extraction.runner = None
    application.state.settings.extraction_backend = "queue"
    with TestClient(application) as test_client:
        response = test_client.post(
            "/api/v1/extract",
            headers={"X-API-Key": settings.dev_api_key},
            json={"url": SAMPLE},
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXTRACTION_FAILED"
    assert unused  # referenced so the guard stays obvious


async def test_extraction_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProc:
        pid = 987654321
        killed = False

        async def communicate(self, payload: bytes):
            del payload
            await asyncio.sleep(5)
            return b"", b""

        def kill(self) -> None:
            self.killed = True

    fake = FakeProc()

    async def create(*args, **kwargs):
        del args, kwargs
        return fake

    monkeypatch.setattr("app.services.extraction.asyncio.create_subprocess_exec", create)
    settings = Settings(extraction_timeout_seconds=1, extraction_socket_timeout_seconds=1)
    with pytest.raises(APIError) as caught:
        await run_local_extractor("https://archive.org/details/BigBuckBunny_124", settings)
    assert caught.value.code == "EXTRACTION_TIMEOUT"
    assert fake.killed is True


def _runner():
    async def runner(url: str, settings_obj: Settings):
        del url, settings_obj
        return {
            "title": "Licensed Sample",
            "duration": 32,
            "thumbnail": None,
            "platform": "ArchiveOrg",
            "is_live": False,
            "formats": [
                {
                    "format_id": "progressive",
                    "ext": "mp4",
                    "container": "mp4",
                    "video_codec": "h264",
                    "audio_codec": "aac",
                    "width": 1280,
                    "height": 720,
                    "fps": 30,
                    "audio_bitrate": 128,
                    "filesize": 1000,
                    "filesize_approximate": False,
                    "has_video": True,
                    "has_audio": True,
                    "requires_merge": False,
                    "delivery_compatible": True,
                    "protocol": "https",
                    "quality": "720p",
                    "url": "https://cdn.example.net/video.mp4",
                    "http_headers": {"User-Agent": "ZIM"},
                    "tbr": 800,
                    "conversion_required": False,
                    "note": None,
                }
            ],
        }

    return runner


def _resolver():
    from tests.conftest import public_resolver

    return public_resolver

