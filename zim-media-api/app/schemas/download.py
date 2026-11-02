"""Download ticket requests."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DownloadLinkRequest(BaseModel):
    extraction_id: str = Field(min_length=4, max_length=80)
    format_id: str = Field(min_length=1, max_length=120)
    delivery: Literal["auto", "direct", "redirect", "proxy"] = "auto"


class CreateKeyRequest(BaseModel):
    name: str | None = Field(default=None, max_length=80)
