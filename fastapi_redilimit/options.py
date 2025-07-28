from dataclasses import dataclass
from enum import StrEnum


class RateLimitStrategy(StrEnum):
    IP = "ip"
    USER_AGENT = "user_agent"
    FINGERPRINT = "fingerprint"
    CUSTOM = "custom"


@dataclass(slots=True, frozen=True, kw_only=True)
class RateLimitConfig:
    requests: int
    window_seconds: int
    strategy: RateLimitStrategy = RateLimitStrategy.IP
    key_prefix: str = "ratelimit"

    def __post_init__(self) -> None:
        if self.requests <= 0:
            raise ValueError("requests must be a positive integer")

        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be a positive integer")


@dataclass(slots=True, kw_only=True)
class RateLimitResult:
    """Result of rate limit check."""

    allowed: bool
    current_requests: int
    limit: int
    window_seconds: int
    reset_time: int
    retry_after: int | None = None

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.current_requests)
