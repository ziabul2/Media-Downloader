"""API key generation and hashing. Plaintext keys are never stored."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_api_key() -> str:
    return "zim_" + secrets.token_urlsafe(32)


def generate_ticket() -> str:
    return secrets.token_urlsafe(32)


def key_prefix(key: str) -> str:
    return key[:12]


def hash_api_key(key: str, pepper: str) -> str:
    return hmac.new(pepper.encode("utf-8"), key.encode("utf-8"), hashlib.sha256).hexdigest()


def hashes_match(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
