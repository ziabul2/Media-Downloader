"""Format selection must not relabel containers or hide a missing audio track."""

from __future__ import annotations

import pytest

from app.core.exceptions import APIError
from app.extractors.ytdlp import build_ydl_options, normalize_format, normalize_info
from app.services.format_selector import select_formats


def _fmt(**overrides):
    base = {
        "format_id": "x",
        "ext": "mp4",
        "container": "mp4",
        "video_codec": "h264",
        "audio_codec": "aac",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "audio_bitrate": 128,
        "filesize": 10,
        "filesize_approximate": False,
        "has_video": True,
        "has_audio": True,
        "requires_merge": False,
        "delivery_compatible": True,
        "protocol": "https",
        "quality": "720p",
        "url": "https://cdn.example.net/v.mp4",
        "http_headers": None,
        "tbr": 100,
        "conversion_required": False,
        "note": None,
    }
    base.update(overrides)
    return base


def test_options_never_download(tmp_path) -> None:
    options = build_ydl_options(15, str(tmp_path))
    assert options["skip_download"] is True
    assert options["noplaylist"] is True
    assert options["geo_bypass"] is False


def test_normalize_skips_storyboards_and_maps_codecs() -> None:
    assert normalize_format({"format_id": "sb0", "ext": "mhtml", "vcodec": "none", "acodec": "none"}, 0) is None
    row = normalize_format(
        {
            "format_id": "22",
            "ext": "mp4",
            "vcodec": "avc1.64001F",
            "acodec": "mp4a.40.2",
            "height": 720,
            "width": 1280,
            "protocol": "https",
            "url": "https://cdn.example.net/a.mp4?signature=sekret",
            "filesize": 50,
            "abr": 128,
        },
        0,
    )
    assert row is not None
    assert row["video_codec"] == "h264"
    assert row["audio_codec"] == "aac"
    assert row["has_audio"] is True
    assert row["requires_merge"] is False
    assert row["delivery_compatible"] is True


def test_video_only_requires_merge() -> None:
    row = normalize_format(
        {
            "format_id": "137",
            "ext": "mp4",
            "vcodec": "avc1",
            "acodec": "none",
            "height": 1080,
            "protocol": "https",
            "url": "https://cdn.example.net/v.mp4",
        },
        0,
    )
    assert row["has_audio"] is False
    assert row["requires_merge"] is True
    assert row["delivery_compatible"] is False


def test_hls_is_not_a_direct_file() -> None:
    row = normalize_format(
        {
            "format_id": "hls",
            "ext": "mp4",
            "vcodec": "avc1",
            "acodec": "mp4a",
            "protocol": "m3u8_native",
            "url": "https://cdn.example.net/index.m3u8",
            "height": 720,
        },
        0,
    )
    assert row["delivery_compatible"] is False


def test_mp4_prefers_progressive_and_reports_substitution() -> None:
    formats = [
        _fmt(format_id="22", height=720, quality="720p"),
        _fmt(
            format_id="137",
            height=1080,
            quality="1080p",
            has_audio=False,
            audio_codec=None,
            requires_merge=True,
            delivery_compatible=False,
        ),
        _fmt(
            format_id="140",
            ext="m4a",
            container="m4a",
            has_video=False,
            video_codec=None,
            height=None,
            width=None,
            quality="128kbps",
            requires_merge=False,
        ),
    ]
    chosen = select_formats(formats, preferred_format="mp4", preferred_quality="1080p", media_type="video")
    assert chosen["selection"]["recommended_format_id"] == "22"
    assert chosen["selection"]["substituted"] is True
    assert chosen["selection"]["actual_quality"] == "720p"
    assert chosen["selection"]["higher_quality_requires_merge"] is True
    assert chosen["selection"]["requires_merge"] is False
    public = {item["format_id"]: item for item in chosen["formats"]}
    assert public["137"]["has_audio"] is False
    assert public["137"]["requires_merge"] is True
    assert "url" not in public["22"]


def test_m4a_reports_source_container() -> None:
    formats = [
        _fmt(
            format_id="140",
            ext="m4a",
            container="m4a",
            has_video=False,
            video_codec=None,
            height=None,
            quality="128kbps",
        )
    ]
    chosen = select_formats(formats, preferred_format="m4a", preferred_quality="audio", media_type="audio")
    assert chosen["selection"]["actual_ext"] == "m4a"
    assert chosen["selection"]["conversion_required"] is False


def test_mp3_is_not_a_renamed_m4a() -> None:
    formats = [
        _fmt(
            format_id="140",
            ext="m4a",
            container="m4a",
            has_video=False,
            video_codec=None,
            audio_codec="aac",
            height=None,
            quality="128kbps",
        )
    ]
    chosen = select_formats(formats, preferred_format="mp3", preferred_quality="audio", media_type="audio")
    assert chosen["selection"]["conversion_required"] is True
    assert chosen["selection"]["actual_ext"] == "m4a"
    assert chosen["selection"]["substituted"] is True
    assert "not renamed" in chosen["selection"]["note"].lower() or "not renamed" in chosen["selection"]["note"]


def test_real_mp3_is_reported_as_mp3() -> None:
    formats = [
        _fmt(
            format_id="mp3a",
            ext="mp3",
            container="mp3",
            has_video=False,
            video_codec=None,
            audio_codec="mp3",
            height=None,
            quality="192kbps",
        )
    ]
    chosen = select_formats(formats, preferred_format="mp3", preferred_quality="audio", media_type="audio")
    assert chosen["selection"]["conversion_required"] is False
    assert chosen["selection"]["actual_ext"] == "mp3"


def test_original_reports_split_streams() -> None:
    formats = [
        _fmt(format_id="22", height=720, quality="720p"),
        _fmt(
            format_id="137",
            height=1080,
            quality="1080p",
            has_audio=False,
            audio_codec=None,
            requires_merge=True,
            delivery_compatible=False,
            tbr=4000,
        ),
        _fmt(
            format_id="140",
            ext="m4a",
            container="m4a",
            has_video=False,
            video_codec=None,
            height=None,
            audio_bitrate=160,
            quality="160kbps",
        ),
    ]
    chosen = select_formats(formats, preferred_format="original", preferred_quality="best", media_type="video")
    assert chosen["selection"]["higher_quality_requires_merge"] is True
    assert chosen["selection"]["merge_components"]["video_format_id"] == "137"
    assert chosen["selection"]["recommended_format_id"] == "22"
    assert "separate" in chosen["selection"]["note"]


def test_playlist_is_rejected() -> None:
    with pytest.raises(APIError) as caught:
        normalize_info({"_type": "playlist", "entries": [], "title": "Nope"})
    assert caught.value.code == "UNSUPPORTED_PLATFORM"
