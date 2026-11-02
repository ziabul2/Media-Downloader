"""Validate Range headers before they are forwarded upstream."""

from __future__ import annotations

import re

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_SAFE_TOKEN = re.compile(r"^[\w!#$&^_.+-]+/[\w!#$&^_.+-]+$")


def forward_range(header: str | None) -> str | None:
    if not header:
        return None
    value = header.strip()
    match = _RANGE.match(value)
    if not match:
        return None
    start, end = match.group(1), match.group(2)
    if start == "" and end == "":
        return None
    if start and end and int(end) < int(start):
        return None
    return f"bytes={start}-{end}"


def safe_content_type(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    cleaned = value.split(";")[0].strip().lower()
    if _SAFE_TOKEN.match(cleaned):
        return cleaned
    return fallback


def content_disposition(filename: str) -> str:
    cleaned = filename.replace('"', "").replace("\r", "").replace("\n", "")
    return f'attachment; filename="{cleaned}"'
