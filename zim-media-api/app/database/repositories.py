"""Key lookup and usage writes. Raw media URLs are not accepted here."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import ApiKey, Developer, QuotaPlan, UsageEvent


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def get_key_by_hash(db: Session, key_hash: str) -> ApiKey | None:
    return db.scalar(select(ApiKey).where(ApiKey.key_hash == key_hash))


def touch_key(db: Session, row: ApiKey) -> None:
    row.last_used_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()


def insert_key(
    db: Session,
    *,
    developer_id: str,
    key_hash: str,
    key_prefix: str,
    role: str,
) -> ApiKey:
    row = ApiKey(
        id=new_id("key"),
        developer_id=developer_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        role=role,
        status="active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revoke_key(db: Session, row: ApiKey) -> None:
    row.status = "revoked"
    row.revoked_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()


def list_keys(db: Session, developer_id: str) -> list[ApiKey]:
    return list(db.scalars(select(ApiKey).where(ApiKey.developer_id == developer_id)).all())


def record_usage(
    db: Session,
    *,
    developer_id: str,
    api_key_id: str,
    endpoint: str,
    status_code: int,
    duration_ms: int,
    delivery_method: str | None,
) -> None:
    db.add(
        UsageEvent(
            id=new_id("use"),
            developer_id=developer_id,
            api_key_id=api_key_id,
            endpoint=endpoint[:80],
            status_code=status_code,
            duration_ms=max(0, duration_ms),
            delivery_method=delivery_method,
        )
    )
    db.commit()


def usage_summary(db: Session, developer_id: str) -> dict:
    total = db.scalar(
        select(func.count()).select_from(UsageEvent).where(UsageEvent.developer_id == developer_id)
    )
    by_endpoint = db.execute(
        select(UsageEvent.endpoint, func.count())
        .where(UsageEvent.developer_id == developer_id)
        .group_by(UsageEvent.endpoint)
    ).all()
    return {
        "total_events": int(total or 0),
        "by_endpoint": {endpoint: int(count) for endpoint, count in by_endpoint},
    }


def ensure_default_plan(db: Session, settings_like: object) -> QuotaPlan:
    existing = db.scalar(select(QuotaPlan).where(QuotaPlan.name == "default"))
    if existing:
        return existing
    plan = QuotaPlan(
        id="plan_default",
        name="default",
        requests_per_minute=settings_like.requests_per_minute,  # type: ignore[attr-defined]
        requests_per_day=settings_like.requests_per_day,  # type: ignore[attr-defined]
        max_concurrent_extractions=settings_like.max_concurrent_extractions,  # type: ignore[attr-defined]
        max_concurrent_streams=settings_like.max_concurrent_streams,  # type: ignore[attr-defined]
    )
    db.add(plan)
    db.commit()
    return plan


def ensure_developer(db: Session, *, name: str, email: str | None = None) -> Developer:
    row = db.scalar(select(Developer).where(Developer.name == name))
    if row:
        return row
    row = Developer(id=new_id("dev"), name=name, email=email, status="active")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
