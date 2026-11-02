"""Tickets, redirects, and revocation. The redirect does not proxy media bytes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.api.deps import Principal, rate_limited, require_api_key
from app.core.exceptions import APIError
from app.core.url_validation import validate_url
from app.schemas.download import DownloadLinkRequest
from app.schemas.response import ok
from app.services.download_manager import build_download
from app.services.ticket_manager import get_ticket, revoke_ticket

router = APIRouter()

_NO_STORE = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex",
}


@router.post("/download-link")
def download_link(
    body: DownloadLinkRequest,
    request: Request,
    principal: Principal = Depends(rate_limited),
) -> dict:
    data = build_download(
        store=request.app.state.store,
        settings=request.app.state.settings,
        extraction_id=body.extraction_id,
        format_id=body.format_id,
        delivery=body.delivery,
        owner_key_id=principal.id,
        public_base_url=request.app.state.settings.public_base_url,
        resolver=request.app.state.resolver,
    )
    request.state.delivery = data.get("delivery")
    return ok(data)


@router.get("/download/{ticket}")
def download(ticket: str, request: Request):
    settings = request.app.state.settings
    payload = get_ticket(
        request.app.state.store,
        ticket,
        touch=True,
        one_time=settings.ticket_one_time,
    )
    request.state.delivery = payload.get("delivery")
    if payload.get("delivery") == "proxy":
        return RedirectResponse(
            url=f"{settings.api_prefix}/stream/{ticket}",
            status_code=302,
            headers=_NO_STORE,
        )
    validated = validate_url(payload["source_url"], resolver=request.app.state.resolver)
    return RedirectResponse(url=validated.url, status_code=302, headers=_NO_STORE)


@router.get("/download/{ticket}/info")
def ticket_info(
    ticket: str,
    request: Request,
    principal: Principal = Depends(require_api_key),
) -> dict:
    payload = get_ticket(request.app.state.store, ticket)
    if payload.get("owner_key_id") != principal.id and principal.id != "anon":
        raise APIError("FORBIDDEN", "This ticket belongs to another API key.")
    now_expires = payload["expires_at"]
    import time

    return ok(
        {
            "delivery": payload.get("delivery"),
            "filename": payload.get("filename"),
            "format": payload.get("ext"),
            "format_id": payload.get("format_id"),
            "expires_in": max(0, int(now_expires) - int(time.time())),
            "revoked": bool(payload.get("revoked")),
            "requires_non_browser_headers": bool(
                (payload.get("constraints") or {}).get("requires_non_browser_headers")
            ),
        }
    )


@router.delete("/download/{ticket}")
def delete_ticket(
    ticket: str,
    request: Request,
    principal: Principal = Depends(require_api_key),
) -> dict:
    revoke_ticket(request.app.state.store, ticket, owner_key_id=principal.id)
    return ok({"revoked": True})
