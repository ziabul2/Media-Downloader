"""Turn a cached extraction plus a format id into a short-lived ticket."""

from __future__ import annotations

from app.config import Settings
from app.core.exceptions import APIError
from app.services.delivery_manager import assess_delivery
from app.services.extraction import load_extraction
from app.services.format_selector import safe_filename
from app.services.store import Store
from app.services.ticket_manager import create_ticket, public_ticket

_CONTENT_TYPES = {
    "mp4": "video/mp4",
    "m4a": "audio/mp4",
    "mp3": "audio/mpeg",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
    "ogg": "audio/ogg",
    "opus": "audio/ogg",
}


def find_format(record: dict, format_id: str) -> dict:
    for fmt in record.get("formats") or []:
        if fmt.get("format_id") == format_id:
            return fmt
    raise APIError("FORMAT_UNAVAILABLE", "The requested format is not available.")


def build_download(
    *,
    store: Store,
    settings: Settings,
    extraction_id: str,
    format_id: str,
    delivery: str,
    owner_key_id: str,
    public_base_url: str,
    resolver=None,
) -> dict:
    record = load_extraction(store, extraction_id)
    fmt = find_format(record, format_id)
    if record.get("is_live"):
        raise APIError("DELIVERY_UNAVAILABLE", "Live media is not delivered as a file.")
    decision = assess_delivery(fmt, delivery, settings, resolver=resolver)
    ext = fmt.get("ext") or "bin"
    filename = safe_filename(record.get("title"), ext)
    ticket = create_ticket(
        store,
        settings,
        {
            "owner_key_id": owner_key_id,
            "source_url": fmt.get("url"),
            "required_headers": fmt.get("http_headers") or {},
            "format_id": format_id,
            "filename": filename,
            "ext": ext,
            "content_type": _CONTENT_TYPES.get(ext, "application/octet-stream"),
            "delivery": decision["delivery"],
            "expose_url": decision["expose_url"],
            "extraction_id": extraction_id,
            "constraints": decision["constraints"],
        },
    )
    base = public_base_url.rstrip("/")
    download_url = f"{base}{settings.api_prefix}/download/{ticket['ticket']}"
    return public_ticket(ticket, download_url=download_url)
