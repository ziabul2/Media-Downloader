"""Logs must not keep API keys, tickets, or signed query parameters."""

from __future__ import annotations

import logging

from app.core.logging import JsonFormatter
from app.core.redaction import redact


def test_redact_signed_url_and_key() -> None:
    raw = (
        "GET /api/v1/download/abcDEFghijKLMNOPQRSTUVWXYZ0123456789 "
        "X-API-Key: zim_supersecretvalue12 "
        "https://cdn.example/v.mp4?signature=sekret&expire=123&token=abcd"
    )
    cleaned = redact(raw)
    assert "supersecret" not in cleaned
    assert "sekret" not in cleaned
    assert "abcDEFghij" not in cleaned
    assert "[REDACTED]" in cleaned


def test_formatter_redacts_records() -> None:
    record = logging.LogRecord(
        name="zim",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="authorization: Bearer zim_anothersecretkey99",
        args=(),
        exc_info=None,
    )
    rendered = JsonFormatter().format(record)
    assert "anothersecretkey99" not in rendered
    assert "Bearer [REDACTED]" in rendered or "zim_[REDACTED]" in rendered
