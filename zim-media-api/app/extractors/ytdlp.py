"""yt-dlp adapter. Metadata only: skip_download is mandatory and media is not written."""

from __future__ import annotations

import re
from typing import Any

from app.core.exceptions import APIError
from app.extractors.registry import select_extractor_name

_CODEC_MAP = {
    "avc1": "h264",
    "h264": "h264",
    "hev1": "hevc",
    "hvc1": "hevc",
    "vp9": "vp9",
    "vp09": "vp9",
    "av01": "av1",
    "mp4a": "aac",
    "aac": "aac",
    "opus": "opus",
    "vorbis": "vorbis",
    "mp3": "mp3",
    "ac-3": "ac3",
    "ec-3": "eac3",
}
_SKIP_EXT = {"mhtml", "jpg", "jpeg", "png", "webp", "srt", "vtt", "json"}
_DIRECT_PROTOCOLS = {"http", "https"}


def build_ydl_options(socket_timeout: int, temp_dir: str) -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": socket_timeout,
        "noprogress": True,
        "nocheckcertificate": False,
        "geo_bypass": False,
        "extract_flat": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "cachedir": False,
        "paths": {"home": temp_dir, "temp": temp_dir},
        "outtmpl": f"{temp_dir}/unused.%(ext)s",
        "restrictfilenames": True,
    }


def simplify_codec(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    short = text.split(".")[0].lower()
    return _CODEC_MAP.get(short, short)


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quality(height: int | None, audio_bitrate: float | None, has_video: bool) -> str | None:
    if has_video and height:
        return f"{height}p"
    if audio_bitrate:
        return f"{int(audio_bitrate)}kbps"
    return None


def normalize_format(raw: dict, index: int) -> dict | None:
    ext = (raw.get("ext") or "") or None
    if isinstance(ext, str):
        ext = ext.lower()
    note = str(raw.get("format_note") or "").lower()
    format_id = str(raw.get("format_id") or f"fmt_{index}")
    if ext in _SKIP_EXT or "storyboard" in note or format_id.startswith("sb"):
        return None
    video_codec = simplify_codec(raw.get("vcodec"))
    audio_codec = simplify_codec(raw.get("acodec"))
    if video_codec is None and audio_codec is None:
        return None
    protocol = raw.get("protocol")
    if isinstance(protocol, str):
        protocol = protocol.lower()
    else:
        protocol = None
    height = _int_or_none(raw.get("height"))
    width = _int_or_none(raw.get("width"))
    filesize = _int_or_none(raw.get("filesize"))
    approximate = False
    if filesize is None:
        approx = _int_or_none(raw.get("filesize_approx"))
        if approx is not None:
            filesize = approx
            approximate = True
    has_video = video_codec is not None
    has_audio = audio_codec is not None
    headers = raw.get("http_headers") if isinstance(raw.get("http_headers"), dict) else None
    safe_headers = None
    if headers:
        safe_headers = {}
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            if any(char in key or char in value for char in ("\r", "\n")):
                continue
            if key.lower() in {"cookie", "set-cookie", "authorization", "proxy-authorization"}:
                continue
            safe_headers[key] = value
    return {
        "format_id": format_id,
        "ext": ext,
        "container": ext,
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "width": width,
        "height": height,
        "fps": _float_or_none(raw.get("fps")),
        "audio_bitrate": _float_or_none(raw.get("abr")),
        "filesize": filesize,
        "filesize_approximate": approximate,
        "has_video": has_video,
        "has_audio": has_audio,
        "requires_merge": has_video and not has_audio,
        "delivery_compatible": bool(
            protocol in _DIRECT_PROTOCOLS and raw.get("url") and not (has_video and not has_audio)
        ),
        "protocol": protocol,
        "quality": _quality(height, _float_or_none(raw.get("abr")), has_video),
        "url": raw.get("url") if isinstance(raw.get("url"), str) else None,
        "http_headers": safe_headers,
        "tbr": _float_or_none(raw.get("tbr")),
        "conversion_required": False,
        "note": None,
    }


def map_extractor_error(exc: Exception) -> APIError:
    text = str(exc).lower()
    if any(word in text for word in ("private", "sign in", "login", "members-only", "members only")):
        return APIError(
            "PRIVATE_MEDIA",
            "This media is private or requires an account. ZIM does not bypass access controls.",
        )
    if "drm" in text:
        return APIError("PRIVATE_MEDIA", "DRM-protected media is not supported.")
    if any(word in text for word in ("geo", "not available in your country", "blocked it in your country")):
        return APIError(
            "VIDEO_UNAVAILABLE",
            "The media is not available from this network. ZIM does not bypass geographic restrictions.",
        )
    if any(word in text for word in ("unavailable", "not available", "removed", "deleted", "does not exist")):
        return APIError("VIDEO_UNAVAILABLE", "The media is unavailable.")
    if "unsupported url" in text:
        return APIError("UNSUPPORTED_PLATFORM", "This URL is not supported.")
    if isinstance(exc, APIError):
        return exc
    return APIError("EXTRACTION_FAILED", "Extraction failed.")


def normalize_info(info: dict) -> dict:
    if not isinstance(info, dict):
        raise APIError("EXTRACTION_FAILED", "Extraction returned nothing usable.")
    if info.get("_type") == "playlist" or (info.get("entries") and not info.get("formats")):
        raise APIError(
            "UNSUPPORTED_PLATFORM",
            "Playlists are not supported. Submit one media URL.",
        )
    formats = []
    for index, raw in enumerate(info.get("formats") or []):
        if isinstance(raw, dict):
            normalized = normalize_format(raw, index)
            if normalized:
                formats.append(normalized)
    # de-duplicate format ids
    seen: dict[str, int] = {}
    for item in formats:
        fid = item["format_id"]
        count = seen.get(fid, 0)
        seen[fid] = count + 1
        if count:
            item["format_id"] = f"{fid}_{count}"
    title = info.get("title")
    if isinstance(title, str):
        title = re.sub(r"\s+", " ", title).strip()[:300] or None
    else:
        title = None
    duration = info.get("duration")
    try:
        duration = int(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration = None
    thumbnail = info.get("thumbnail") if isinstance(info.get("thumbnail"), str) else None
    return {
        "title": title,
        "duration": duration,
        "thumbnail": thumbnail,
        "platform": (info.get("extractor_key") or info.get("extractor") or "unknown"),
        "media_id": str(info.get("id") or "")[:120] or None,
        "is_live": bool(info.get("is_live")),
        "was_live": bool(info.get("was_live")),
        "formats": formats,
    }


def extract_with_ytdlp(
    url: str,
    *,
    prefixes: list[str],
    allow_generic: bool,
    socket_timeout: int,
    temp_dir: str,
) -> dict:
    select_extractor_name(url, prefixes, allow_generic)
    import yt_dlp

    options = build_ydl_options(socket_timeout, temp_dir)
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except APIError:
        raise
    except Exception as exc:
        raise map_extractor_error(exc) from exc
    if not isinstance(info, dict):
        raise APIError("EXTRACTION_FAILED", "Extraction returned nothing usable.")
    availability = str(info.get("availability") or "").lower()
    if availability in {"private", "subscriber_only", "needs_auth", "premium_only"}:
        raise APIError(
            "PRIVATE_MEDIA",
            "This media is private or requires an account. ZIM does not bypass access controls.",
        )
    return normalize_info(info)
