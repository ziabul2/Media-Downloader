"""List formats and check whether a choice can actually be delivered."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import Principal, rate_limited
from app.schemas.extraction import FormatChoice
from app.schemas.response import ok
from app.services.delivery_manager import assess_delivery
from app.services.download_manager import find_format
from app.services.extraction import load_extraction
from app.services.format_selector import public_format

router = APIRouter()


@router.get("/formats/{extraction_id}")
def list_formats(
    extraction_id: str,
    request: Request,
    principal: Principal = Depends(rate_limited),
) -> dict:
    del principal
    record = load_extraction(request.app.state.store, extraction_id)
    return ok(
        {
            "extraction_id": extraction_id,
            "formats": record.get("public_formats") or [],
            "selection": record.get("selection"),
        }
    )


@router.post("/formats/select")
def select_format(
    body: FormatChoice,
    request: Request,
    principal: Principal = Depends(rate_limited),
) -> dict:
    del principal
    record = load_extraction(request.app.state.store, body.extraction_id)
    fmt = find_format(record, body.format_id)
    try:
        decision = assess_delivery(
            fmt,
            body.delivery,
            request.app.state.settings,
            resolver=request.app.state.resolver,
        )
        delivery = {
            "available": True,
            "delivery": decision["delivery"],
            "note": (decision.get("constraints") or {}).get("note"),
        }
    except Exception as exc:
        from app.core.exceptions import APIError

        if not isinstance(exc, APIError):
            raise
        delivery = {"available": False, "delivery": None, "code": exc.code, "note": exc.message}
    return ok({"format": public_format(fmt), "delivery": delivery})
