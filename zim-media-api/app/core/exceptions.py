"""Stable API errors. Client messages never include upstream bodies or secrets."""

from __future__ import annotations


class APIError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code or STATUS_BY_CODE.get(code, 400)
        self.retryable = retryable


STATUS_BY_CODE: dict[str, int] = {
    "INVALID_URL": 400,
    "UNSUPPORTED_SCHEME": 400,
    "UNSUPPORTED_PLATFORM": 422,
    "BLOCKED_DESTINATION": 400,
    "VIDEO_UNAVAILABLE": 404,
    "PRIVATE_MEDIA": 403,
    "EXTRACTION_FAILED": 502,
    "EXTRACTION_TIMEOUT": 504,
    "FORMAT_UNAVAILABLE": 404,
    "MEDIA_URL_EXPIRED": 410,
    "DELIVERY_UNAVAILABLE": 409,
    "PROXY_NOT_ALLOWED": 403,
    "RATE_LIMIT_EXCEEDED": 429,
    "QUOTA_EXCEEDED": 429,
    "INVALID_TICKET": 404,
    "TICKET_EXPIRED": 410,
    "UPSTREAM_ERROR": 502,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "INVALID_REQUEST": 400,
    "INTERNAL_ERROR": 500,
}
