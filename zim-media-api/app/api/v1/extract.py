"""Metadata extraction. The route does not call yt-dlp itself."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import Principal, rate_limited
from app.schemas.extraction import ExtractRequest
from app.schemas.response import ok
from app.services.extraction import public_extraction

router = APIRouter()


@router.post("/extract")
async def extract(
    body: ExtractRequest,
    request: Request,
    principal: Principal = Depends(rate_limited),
) -> dict:
    del principal
    record = await request.app.state.extraction.extract(
        url=body.url,
        media_type=body.media_type,
        preferred_format=body.preferred_format,
        preferred_quality=body.preferred_quality,
        settings=request.app.state.settings,
        store=request.app.state.store,
        slots=request.app.state.extract_slots,
        resolver=request.app.state.resolver,
    )
    return ok(record)


@router.get("/extract/{extraction_id}")
def get_extract(
    extraction_id: str,
    request: Request,
    principal: Principal = Depends(rate_limited),
) -> dict:
    del principal
    from app.services.extraction import load_extraction

    return ok(public_extraction(load_extraction(request.app.state.store, extraction_id)))
