"""Redact secrets, signed URLs, cookies, and ticket values before they are logged."""

from __future__ import annotations

import re

_KEY = re.compile(r"zim_[A-Za-z0-9_\-]{8,}")
_HEADER = re.compile(
    r"(?i)\b(x-api-key|authorization|api[_-]?key|cookie|set-cookie|proxy-authorization)\b\s*[:=]\s*([^\s,;]+)"
)
_QUERY = re.compile(
    r"(?i)([?&](?:signature|sig|lsig|expire|expires|token|playback|auth|password|secret|key|api_key|n|source|ip|s|gir|ratebypass)=)[^&\s\"']+"
)
_TICKET_PATH = re.compile(r"(?i)(/(?:download|stream)/)[^/\s\"'?]+")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")


def redact(value: object) -> str:
    text = value if isinstance(value, str) else str(value)
    text = _HEADER.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _QUERY.sub(r"\1[REDACTED]", text)
    text = _TICKET_PATH.sub(r"\1[REDACTED]", text)
    text = _KEY.sub("zim_[REDACTED]", text)
    return text
