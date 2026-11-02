"""Only the approved extractor may run. Generic URLs are rejected before fetch."""

from __future__ import annotations

import pytest

from app.core.exceptions import APIError
from app.extractors.registry import extractor_allowed, select_extractor_name

PREFIXES = ["youtube", "vimeo", "soundcloud", "archive.org"]


def test_generic_is_blocked() -> None:
    with pytest.raises(APIError) as caught:
        select_extractor_name("https://example.com/video.mp4", PREFIXES, allow_generic=False)
    assert caught.value.code == "UNSUPPORTED_PLATFORM"


def test_youtube_watch_is_allowed() -> None:
    name = select_extractor_name(
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        PREFIXES,
        allow_generic=False,
    )
    assert name == "youtube"


def test_archive_is_allowed() -> None:
    name = select_extractor_name(
        "https://archive.org/details/BigBuckBunny_124",
        PREFIXES,
        allow_generic=False,
    )
    assert name == "archive.org"


def test_prefix_helper() -> None:
    assert extractor_allowed("youtube:playlist", PREFIXES, False)
    assert extractor_allowed("generic", PREFIXES, False) is False
    assert extractor_allowed("generic", PREFIXES, True) is True
