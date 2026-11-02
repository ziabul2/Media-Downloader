"""Extraction and format-selection contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    media_type: Literal["video", "audio"] = "video"
    preferred_format: Literal["mp4", "m4a", "mp3", "original"] = "mp4"
    preferred_quality: str | None = "1080p"


class FormatChoice(BaseModel):
    extraction_id: str = Field(min_length=4, max_length=80)
    format_id: str = Field(min_length=1, max_length=120)
    delivery: Literal["auto", "direct", "redirect", "proxy"] = "auto"
