"""Extractor interface. Additional adapters register against this protocol."""

from __future__ import annotations

from typing import Protocol


class Extractor(Protocol):
    name: str

    def supports(self, url: str) -> bool: ...

    def extract(self, url: str) -> dict: ...
