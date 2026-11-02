"""Short-lived records: extraction metadata, tickets, and rate-limit counters.

Redis is used when it answers a ping. A single-process memory store is the
development fallback and is refused in production by settings validation.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Protocol

import redis


class Store(Protocol):
    def set_json(self, key: str, value: dict, ttl: int) -> None: ...

    def get_json(self, key: str) -> dict | None: ...

    def delete(self, key: str) -> None: ...

    def incr(self, key: str, ttl: int) -> int: ...


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, tuple[str, float | None]] = {}
        self.backend = "memory"

    def _purge(self, key: str, now: float) -> None:
        row = self._values.get(key)
        if row is None:
            return
        _, expires = row
        if expires is not None and expires <= now:
            self._values.pop(key, None)

    def set_json(self, key: str, value: dict, ttl: int) -> None:
        payload = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
        with self._lock:
            self._values[key] = (payload, time.time() + ttl)

    def get_json(self, key: str) -> dict | None:
        with self._lock:
            self._purge(key, time.time())
            row = self._values.get(key)
            if row is None:
                return None
            return json.loads(row[0])

    def delete(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)

    def incr(self, key: str, ttl: int) -> int:
        now = time.time()
        with self._lock:
            self._purge(key, now)
            row = self._values.get(key)
            current = int(row[0]) if row else 0
            current += 1
            expires = row[1] if row and row[1] else now + ttl
            self._values[key] = (str(current), expires)
            return current


class RedisStore:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client
        self.backend = "redis"

    def set_json(self, key: str, value: dict, ttl: int) -> None:
        payload = json.dumps(value, separators=(",", ":"), ensure_ascii=True)
        self._client.set(key, payload, ex=ttl)

    def get_json(self, key: str) -> dict | None:
        raw = self._client.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def incr(self, key: str, ttl: int) -> int:
        count = int(self._client.incr(key))
        if count == 1:
            self._client.expire(key, ttl)
        return count


def build_store(redis_url: str, *, required: bool) -> Store:
    if not redis_url:
        if required:
            raise RuntimeError("Redis is required but REDIS_URL is empty")
        return MemoryStore()
    client = redis.Redis.from_url(redis_url, socket_connect_timeout=0.4, socket_timeout=0.4)
    try:
        client.ping()
    except redis.RedisError as exc:
        if required:
            raise RuntimeError("Redis is required but did not respond") from exc
        return MemoryStore()
    return RedisStore(client)
