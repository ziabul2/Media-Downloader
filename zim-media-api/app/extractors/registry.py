"""Allow-list of extractor names. Generic fetching stays off unless configured."""

from __future__ import annotations

from app.core.exceptions import APIError


def extractor_allowed(ie_name: str, prefixes: list[str], allow_generic: bool) -> bool:
    name = (ie_name or "").lower()
    if name == "generic":
        return allow_generic
    for prefix in prefixes:
        if name == prefix or name.startswith(prefix + ":") or name.startswith(prefix):
            return True
    return False


def select_extractor_name(url: str, prefixes: list[str], allow_generic: bool) -> str:
    import yt_dlp

    ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noprogress": True})
    for ie in ydl._ies.values():
        if ie.suitable(url):
            if not extractor_allowed(ie.IE_NAME, prefixes, allow_generic):
                raise APIError(
                    "UNSUPPORTED_PLATFORM",
                    "This platform is not enabled. ZIM only extracts an approved set of public sources.",
                )
            return ie.IE_NAME
    raise APIError(
        "UNSUPPORTED_PLATFORM",
        "No approved extractor matches this URL.",
    )


def supported_platforms(prefixes: list[str]) -> list[dict]:
    labels = {
        "youtube": "YouTube",
        "vimeo": "Vimeo",
        "soundcloud": "SoundCloud",
        "dailymotion": "Dailymotion",
        "archive.org": "Internet Archive",
        "ted": "TED",
        "bandcamp": "Bandcamp",
        "peertube": "PeerTube",
        "wikimedia.org": "Wikimedia Commons",
        "npr": "NPR",
    }
    return [{"id": prefix, "name": labels.get(prefix, prefix)} for prefix in prefixes]
