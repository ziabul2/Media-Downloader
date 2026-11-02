"""Shared dependencies: database sessions, API keys, and rate limits."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.exceptions import APIError
from app.core.rate_limit import enforce_limits
from app.core.security import hash_api_key
from app.database.repositories import get_key_by_hash, touch_key


@dataclass
class Principal:
    id: str
    developer_id: str
    role: str
    prefix: str


def get_db(request: Request):
    db: Session = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def client_ip(request: Request) -> str:
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def require_api_key(
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Principal:
    settings = request.app.state.settings
    if not settings.api_key_required:
        principal = Principal(id="anon", developer_id="anon", role="admin", prefix="anon")
        request.state.principal = principal
        return principal
    if not x_api_key:
        raise APIError("UNAUTHORIZED", "An X-API-Key header is required.")
    digest = hash_api_key(x_api_key, settings.api_key_pepper)
    row = get_key_by_hash(db, digest)
    if row is None or row.status != "active":
        raise APIError("UNAUTHORIZED", "The API key is not valid.")
    touch_key(db, row)
    principal = Principal(
        id=row.id,
        developer_id=row.developer_id,
        role=row.role,
        prefix=row.key_prefix,
    )
    request.state.principal = principal
    return principal


def require_admin(principal: Principal = Depends(require_api_key)) -> Principal:
    if principal.role != "admin":
        raise APIError("FORBIDDEN", "This action requires an owner key.")
    return principal


def rate_limited(request: Request, principal: Principal = Depends(require_api_key)) -> Principal:
    enforce_limits(
        request.app.state.store,
        settings=request.app.state.settings,
        key_id=principal.id,
        client_ip=client_ip(request),
    )
    return principal
