from __future__ import annotations
from typing import TYPE_CHECKING

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from fastapi_redilimit.rate_limiter import RateLimitResult


class HTTPRateLimitReached(HTTPException):
    def __init__(self, result: RateLimitResult) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=result.to_exception_details(),
            headers=result.get_headers(),
        )
