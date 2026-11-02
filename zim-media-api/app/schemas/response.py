"""Consistent JSON envelope."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    request_id: str


class Envelope(BaseModel):
    success: bool
    data: Any | None = None
    error: ErrorBody | None = None


def ok(data: Any) -> dict:
    return {"success": True, "data": data}


def fail(code: str, message: str, request_id: str, retryable: bool = False) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "request_id": request_id,
        },
    }


class HealthData(BaseModel):
    status: str = Field(examples=["ok"])
