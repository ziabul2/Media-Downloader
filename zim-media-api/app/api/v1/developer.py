"""Owner key management. Plaintext keys are returned only at creation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_db, rate_limited, require_admin, require_api_key
from app.core.exceptions import APIError
from app.core.security import generate_api_key, hash_api_key, key_prefix
from app.database.repositories import insert_key, list_keys, revoke_key, usage_summary
from app.database.models import ApiKey
from app.schemas.download import CreateKeyRequest
from app.schemas.response import ok
from sqlalchemy import select

router = APIRouter()


def _key_view(row: ApiKey) -> dict:
    return {
        "id": row.id,
        "key_prefix": row.key_prefix,
        "role": row.role,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }


@router.post("/developer/keys")
def create_key(
    body: CreateKeyRequest,
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    del body
    settings = request.app.state.settings
    plaintext = generate_api_key()
    row = insert_key(
        db,
        developer_id=principal.developer_id,
        key_hash=hash_api_key(plaintext, settings.api_key_pepper),
        key_prefix=key_prefix(plaintext),
        role="standard",
    )
    return ok(
        {
            "id": row.id,
            "api_key": plaintext,
            "key_prefix": row.key_prefix,
            "role": row.role,
            "warning": "Copy this key now. It will not be shown again.",
        }
    )


@router.get("/developer/keys")
def get_keys(
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return ok({"keys": [_key_view(row) for row in list_keys(db, principal.developer_id)]})


@router.post("/developer/keys/{key_id}/revoke")
def revoke(
    key_id: str,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(select(ApiKey).where(ApiKey.id == key_id))
    if row is None or row.developer_id != principal.developer_id:
        raise APIError("FORBIDDEN", "That key does not belong to this account.")
    if row.role == "admin":
        raise APIError("FORBIDDEN", "The owner key cannot be revoked from this endpoint.")
    revoke_key(db, row)
    return ok({"id": row.id, "status": "revoked"})


@router.get("/developer/usage")
def usage(
    principal: Principal = Depends(rate_limited),
    db: Session = Depends(get_db),
) -> dict:
    return ok(usage_summary(db, principal.developer_id))


@router.get("/developer/limits")
def limits(request: Request, principal: Principal = Depends(require_api_key)) -> dict:
    del principal
    settings = request.app.state.settings
    return ok(
        {
            "requests_per_minute": settings.requests_per_minute,
            "requests_per_day": settings.requests_per_day,
            "max_concurrent_extractions": settings.max_concurrent_extractions,
            "max_concurrent_streams": settings.max_concurrent_streams,
            "proxy_enabled": settings.proxy_enabled,
            "ticket_ttl_seconds": settings.default_ticket_ttl_seconds,
            "metadata_ttl_seconds": settings.metadata_cache_ttl_seconds,
        }
    )


@router.get("/developer/dev-session")
def dev_session(request: Request) -> dict:
    settings = request.app.state.settings
    if settings.app_env != "development":
        raise APIError("FORBIDDEN", "Development credentials are not available.")
    key = getattr(request.app.state, "dev_api_key", None)
    if not key:
        raise APIError("FORBIDDEN", "No development key is configured.")
    return ok({"api_key": key, "key_prefix": key[:12], "environment": "development"})
