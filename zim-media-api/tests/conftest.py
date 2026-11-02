"""App fixtures. Extraction is faked; SSRF tests call the validator directly."""

from __future__ import annotations

import ipaddress

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PUBLIC_IP = ipaddress.ip_address("93.184.216.34")


def public_resolver(hostname: str, port: int):
    del port
    text = hostname.strip("[]")
    try:
        return [ipaddress.ip_address(text)]
    except ValueError:
        return [PUBLIC_IP]


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        app_env="development",
        database_url="sqlite://",
        redis_url="",
        redis_required=False,
        api_key_required=True,
        api_key_pepper="test-pepper",
        dev_api_key="zim_test_key_please",
        data_dir=str(tmp_path),
        requests_per_minute=1000,
        requests_per_day=10000,
        proxy_enabled=False,
        public_base_url="",
    )


@pytest.fixture
def app(settings):
    async def runner(url: str, settings_obj: Settings):
        del url, settings_obj
        return {
            "title": "Licensed Sample",
            "duration": 32,
            "thumbnail": "https://cdn.example.net/thumb.jpg",
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
                },
                {
                    "format_id": "video1080",
                    "ext": "mp4",
                    "container": "mp4",
                    "video_codec": "h264",
                    "audio_codec": None,
                    "width": 1920,
                    "height": 1080,
                    "fps": 30,
                    "audio_bitrate": None,
                    "filesize": 2000,
                    "filesize_approximate": False,
                    "has_video": True,
                    "has_audio": False,
                    "requires_merge": True,
                    "delivery_compatible": False,
                    "protocol": "https",
                    "quality": "1080p",
                    "url": "https://cdn.example.net/video1080.mp4",
                    "http_headers": None,
                    "tbr": 2000,
                    "conversion_required": False,
                    "note": None,
                },
                {
                    "format_id": "audio140",
                    "ext": "m4a",
                    "container": "m4a",
                    "video_codec": None,
                    "audio_codec": "aac",
                    "width": None,
                    "height": None,
                    "fps": None,
                    "audio_bitrate": 128,
                    "filesize": 300,
                    "filesize_approximate": False,
                    "has_video": False,
                    "has_audio": True,
                    "requires_merge": False,
                    "delivery_compatible": True,
                    "protocol": "https",
                    "quality": "128kbps",
                    "url": "https://cdn.example.net/audio.m4a",
                    "http_headers": {"User-Agent": "ZIM"},
                    "tbr": 128,
                    "conversion_required": False,
                    "note": None,
                },
            ],
        }

    application = create_app(settings, runner=runner, resolver=public_resolver)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api_key(settings) -> str:
    return settings.dev_api_key


@pytest.fixture
def auth(api_key):
    return {"X-API-Key": api_key}
