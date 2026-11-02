"""Per-key and per-IP counters. Values live in Redis when it is configured."""

from __future__ import annotations

import time

from app.config import Settings
from app.core.exceptions import APIError
from app.services.store import Store


def enforce_limits(
    store: Store,
    *,
    settings: Settings,
    key_id: str,
    client_ip: str,
) -> None:
    minute = int(time.time() // 60)
    day = time.strftime("%Y%m%d", time.gmtime())
    per_minute = store.incr(f"rl:m:{key_id}:{minute}", 120)
    per_ip = store.incr(f"rl:ip:{client_ip}:{minute}", 120)
    per_day = store.incr(f"rl:d:{key_id}:{day}", 172_800)
    if per_minute > settings.requests_per_minute or per_ip > settings.requests_per_minute:
        raise APIError(
            "RATE_LIMIT_EXCEEDED",
            "Too many requests. Wait and try again.",
            retryable=True,
        )
    if per_day > settings.requests_per_day:
        raise APIError(
            "QUOTA_EXCEEDED",
            "The daily request quota is exhausted.",
            retryable=False,
        )
