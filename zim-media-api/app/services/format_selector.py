"""Choose a real source format and say when the request cannot be satisfied as-is."""

from __future__ import annotations

import re

from app.core.exceptions import APIError

PUBLIC_FIELDS = (
    "format_id",
    "ext",
    "container",
    "video_codec",
    "audio_codec",
    "width",
    "height",
    "fps",
    "audio_bitrate",
    "filesize",
    "filesize_approximate",
    "has_video",
    "has_audio",
    "requires_merge",
    "delivery_compatible",
    "protocol",
    "quality",
    "conversion_required",
    "note",
)


def public_format(fmt: dict) -> dict:
    return {key: fmt.get(key) for key in PUBLIC_FIELDS}


def parse_quality(value: str | None) -> int | None:
    if not value or value.lower() in {"best", "original", "audio"}:
        return None
    match = re.search(r"(\d{3,4})", value)
    if not match:
        return None
    return int(match.group(1))


def _better_video(left: dict, right: dict) -> dict:
    left_key = (left.get("height") or 0, left.get("tbr") or 0, left.get("fps") or 0)
    right_key = (right.get("height") or 0, right.get("tbr") or 0, right.get("fps") or 0)
    return left if left_key >= right_key else right


def _better_audio(left: dict, right: dict) -> dict:
    return left if (left.get("audio_bitrate") or 0) >= (right.get("audio_bitrate") or 0) else right


def _closest_progressive(candidates: list[dict], target: int | None) -> dict | None:
    if not candidates:
        return None
    if target is None:
        return max(candidates, key=lambda item: (item.get("height") or 0, item.get("tbr") or 0))

    def rank(item: dict) -> tuple:
        height = item.get("height") or 0
        if height <= target:
            return (0, target - height, -(item.get("tbr") or 0))
        return (1, height - target, -(item.get("tbr") or 0))

    return min(candidates, key=rank)


def _audio_candidates(formats: list[dict], *, prefer_ext: str | None = None) -> list[dict]:
    rows = [item for item in formats if item.get("has_audio") and not item.get("has_video")]
    if prefer_ext:
        preferred = [item for item in rows if item.get("ext") == prefer_ext]
        if preferred:
            return preferred
    return rows


def select_formats(
    formats: list[dict],
    *,
    preferred_format: str,
    preferred_quality: str | None,
    media_type: str,
) -> dict:
    if not formats:
        raise APIError("FORMAT_UNAVAILABLE", "The source did not publish any usable formats.")

    target = parse_quality(preferred_quality)
    videos = [item for item in formats if item.get("has_video")]
    progressive = [
        item
        for item in videos
        if item.get("has_audio") and item.get("ext") == "mp4" and item.get("protocol") in {"http", "https"}
    ]
    any_progressive = [
        item
        for item in videos
        if item.get("has_audio") and item.get("protocol") in {"http", "https"}
    ]
    video_only = [item for item in videos if not item.get("has_audio")]
    best_video = None
    if videos:
        best_video = videos[0]
        for item in videos[1:]:
            best_video = _better_video(best_video, item)
    audios = _audio_candidates(formats)
    best_audio = None
    if audios:
        best_audio = audios[0]
        for item in audios[1:]:
            best_audio = _better_audio(best_audio, item)
    m4a = _audio_candidates(formats, prefer_ext="m4a")
    best_m4a = None
    if m4a:
        best_m4a = m4a[0]
        for item in m4a[1:]:
            best_m4a = _better_audio(best_m4a, item)
    mp3_rows = [
        item
        for item in formats
        if item.get("has_audio")
        and not item.get("has_video")
        and (item.get("ext") == "mp3" or item.get("audio_codec") == "mp3")
    ]
    best_mp3 = None
    if mp3_rows:
        best_mp3 = mp3_rows[0]
        for item in mp3_rows[1:]:
            best_mp3 = _better_audio(best_mp3, item)

    higher_merge = False
    merge_components = None
    if best_video and not best_video.get("has_audio") and best_audio:
        higher_merge = True
        merge_components = {
            "video_format_id": best_video["format_id"],
            "audio_format_id": best_audio["format_id"],
        }

    recommended = None
    substituted = False
    conversion_required = False
    note = None
    requires_merge = False

    if preferred_format == "m4a" or (preferred_format == "original" and media_type == "audio"):
        recommended = best_m4a or best_audio or best_mp3
        if recommended is None:
            raise APIError("FORMAT_UNAVAILABLE", "No audio-only format is available.")
        if recommended.get("ext") != "m4a" and preferred_format == "m4a":
            substituted = True
            note = (
                f"No M4A stream was published. The closest audio source is "
                f"{recommended.get('ext') or 'unknown'} and was not renamed."
            )
    elif preferred_format == "mp3":
        if best_mp3:
            recommended = best_mp3
        else:
            recommended = best_m4a or best_audio
            if recommended is None:
                raise APIError("FORMAT_UNAVAILABLE", "No audio stream is available to convert from.")
            conversion_required = True
            substituted = True
            note = (
                "The source has no MP3 stream. "
                f"The available audio is {recommended.get('ext') or 'unknown'} "
                f"({recommended.get('audio_codec') or 'unknown codec'}). "
                "It was not renamed to .mp3. Server-side conversion is disabled; convert on the client."
            )
    elif preferred_format == "original":
        single = _closest_progressive(any_progressive or progressive, None)
        if best_video and best_video.get("has_audio"):
            recommended = best_video
            requires_merge = False
        elif higher_merge:
            recommended = single or best_video
            requires_merge = single is None
            note = (
                "Original quality is split. The highest video and audio are separate streams, "
                "and this server does not merge them. "
                + (
                    f"The best single file is {single.get('quality') or single.get('format_id')}."
                    if single
                    else "No single file with audio and video is available."
                )
            )
            if single:
                recommended = single
                requires_merge = False
            else:
                recommended = best_video
                requires_merge = True
        else:
            recommended = single or best_video or best_audio
    else:
        # mp4
        chosen = _closest_progressive(progressive, target)
        if chosen is None:
            chosen = _closest_progressive([item for item in any_progressive if item.get("ext") == "mp4"], target)
        if chosen is None and not video_only:
            raise APIError("FORMAT_UNAVAILABLE", "No MP4 video format is available.")
        if chosen is None:
            recommended = _better_video(video_only[0], video_only[0])
            for item in video_only[1:]:
                recommended = _better_video(recommended, item)
            requires_merge = True
            note = (
                "No progressive MP4 with audio was published. "
                "The video stream has no audio and requires a merge this server does not perform."
            )
        else:
            recommended = chosen
            actual_height = chosen.get("height")
            if target and actual_height and actual_height != target:
                substituted = True
                if higher_merge:
                    note = (
                        f"No progressive {target}p MP4 with audio was published. "
                        f"The deliverable file is {actual_height}p. "
                        "A higher video-only stream exists and would require a merge."
                    )
                else:
                    note = (
                        f"No progressive {target}p MP4 was published. "
                        f"The closest deliverable file is {actual_height}p."
                    )

    if recommended is None:
        raise APIError("FORMAT_UNAVAILABLE", "The requested format is not available.")

    if recommended.get("is_live"):
        recommended["delivery_compatible"] = False

    selection = {
        "requested_format": preferred_format,
        "requested_quality": preferred_quality,
        "recommended_format_id": recommended["format_id"],
        "actual_container": recommended.get("container"),
        "actual_ext": recommended.get("ext"),
        "actual_quality": recommended.get("quality"),
        "has_video": bool(recommended.get("has_video")),
        "has_audio": bool(recommended.get("has_audio")),
        "substituted": substituted,
        "requires_merge": bool(requires_merge or recommended.get("requires_merge")),
        "conversion_required": conversion_required,
        "direct_file_available": bool(recommended.get("delivery_compatible") and not requires_merge and not conversion_required),
        "higher_quality_requires_merge": higher_merge,
        "merge_components": merge_components,
        "note": note,
    }
    return {
        "formats": [public_format(item) for item in formats],
        "internal_formats": formats,
        "selection": selection,
    }


def safe_filename(title: str | None, ext: str | None) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", title or "media").strip("-._")[:80] or "media"
    clean_ext = re.sub(r"[^A-Za-z0-9]", "", (ext or "bin").lower())[:8] or "bin"
    return f"{base}.{clean_ext}"
