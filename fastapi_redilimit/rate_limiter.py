from dataclasses import dataclass
from enum import StrEnum
import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi_redilimit.key_generators import (
    AbstractKeyGenerator,
    ClientKeyGenerator,
    IPKeyGenerator,
    UserAgentKeyGenerator,
)
from fastapi import HTTPException, status

if TYPE_CHECKING:
    import redis.asyncio
    from fastapi import Request


class RateLimitStrategy(StrEnum):
    IP = "ip"
    USER_AGENT = "user_agent"
    CLIENT = "client"
    CUSTOM = "custom"


@dataclass(slots=True, frozen=True, kw_only=True)
class RateLimitOptions:
    max_requests: int
    window_seconds: int
    window_hours: int

    def __post_init__(self) -> None:
        if self.max_requests <= 0:
            raise ValueError("requests must be a positive integer")

        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be a positive integer")

        if self.window_hours < 0:
            raise ValueError("window_hours must be a non-negative integer")

    @property
    def total_seconds(self) -> int:
        return self.window_seconds + (self.window_hours * 3600)


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

    def to_exception_details(self) -> dict[str, Any]:
        return {
            "error": "Rate limit exceeded",
            "allowed": self.allowed,
            "window_seconds": self.window_seconds,
            "reset_time": self.reset_time,
            "retry_after": self.retry_after,
        }

    def get_headers(self) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(self.reset_time),
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        return headers


class _Limiter:
    """
    Represents a rate limiter that checks the rate limit for a request.
    """

    def __init__(
        self,
        *,
        redis_connection: redis.asyncio.Redis,
        options: RateLimitOptions,
        key_generator: AbstractKeyGenerator,
    ) -> None:
        self.redis: redis.asyncio.Redis = redis_connection
        self.options: RateLimitOptions = options
        self.key_generator: AbstractKeyGenerator = key_generator

    async def __slide_rate_limit_window(
        self, *, key: str, current_time: float, window_start: float
    ) -> list[Any]:
        """
        Slides the rate limit window by removing old entries and adding the current request.

        Parameters
        ----------
        key : str
            _the redis key_
        current_time : float
            _the time of the request_
        window_start : float
            _the time the window started_

        Returns
        -------
        list[Any]
            _A list containing the results of the pipeline execution, which includes the
            number of requests in the current window._
        """
        async with self.redis.pipeline() as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(current_time): current_time})
            pipe.zcard(key)
            pipe.expire(key, self.options.window_seconds + 1)
            results = await pipe.execute()

        return results

    async def __get_rate_limit(self, request: Request) -> RateLimitResult:
        """
        Checks the rate limit for the given request.
        - Produces a unique key based on the request's context using
        `self.key_generator`.
        - Slides the rate limit window to remove old entries and get
        the current request count.
        - Returns a `RateLimitResult` indicating whether the request is allowed and other details.


        Parameters
        ----------
        request : Request

        Returns
        -------
        RateLimitResult

        Raises
        ------
        HTTPException -- 500, Internal Server Error
            _Only occurs when something is wrong with
            the redis configuration_
        """
        redis_key = await self.key_generator(request)
        current_time = time.time()
        window_start = current_time - self.options.total_seconds
        if window_start < 0:
            window_start = 0

        try:
            results = await self.__slide_rate_limit_window(
                key=redis_key,
                current_time=current_time,
                window_start=window_start,
            )
            request_count = results[2]  # zcard result
        except (IndexError, Exception) as exc:
            logger = logging.getLogger(__name__)
            logger.error(
                "The current request count could not be retrieved "
                "from redis likely due to an index out of bounds error. "
                "This may indicate a misconfiguration or an issue with "
                "the Redis connection.",
                exc_info=exc,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An issue occured while checking rate limits. Please try again later.",
            )

        reset_time = int(current_time + self.options.total_seconds)
        request_allowed = request_count <= self.options.max_requests
        retry_after = None if request_allowed else reset_time - int(current_time)

        return RateLimitResult(
            allowed=request_allowed,
            current_requests=request_count,
            limit=self.options.max_requests,
            window_seconds=self.options.total_seconds,
            reset_time=reset_time,
            retry_after=retry_after,
        )

    async def check(self, request: Request) -> RateLimitResult:
        """
        Public API to check the rate limit for a request.

        Parameters
        ----------
        request : Request

        Returns
        -------
        RateLimitResult
        """
        return await self.__get_rate_limit(request)


def _get_key_generator(
    prefix: str,
    strategy: RateLimitStrategy,
    custom_key_generator: AbstractKeyGenerator | None,
) -> AbstractKeyGenerator:
    match strategy:
        case RateLimitStrategy.IP:
            return IPKeyGenerator(prefix)

        case RateLimitStrategy.USER_AGENT:
            return UserAgentKeyGenerator(prefix)

        case RateLimitStrategy.CLIENT:
            return ClientKeyGenerator(prefix)

        case RateLimitStrategy.CUSTOM:
            if custom_key_generator is None:
                raise ValueError(
                    "Custom key generator must be provided for the CUSTOM strategy"
                )
            return custom_key_generator

        case _:
            raise ValueError(f"Unknown rate limit strategy: {strategy}")


class RedisRateLimiter:
    def __init__(
        self,
        *,
        redis_connection: redis.asyncio.Redis,
        strategy: RateLimitStrategy = RateLimitStrategy.CLIENT,
        redis_key_prefix: str = "ratelimit",
        custom_key_generator: AbstractKeyGenerator | None = None,
    ) -> None:
        self.redis: redis.asyncio.Redis = redis_connection
        self.strategy: RateLimitStrategy = strategy
        self.key_prefix: str = redis_key_prefix
        self.key_generator: AbstractKeyGenerator = _get_key_generator(
            redis_key_prefix, strategy, custom_key_generator
        )

    def create_limiter(
        self,
        *,
        max_requests: int = 100,
        window_seconds: int = 60,
        window_hours: int = 0,
    ) -> _Limiter:
        options = RateLimitOptions(
            max_requests=max_requests,
            window_seconds=window_seconds,
            window_hours=window_hours,
        )

        return _Limiter(
            redis_connection=self.redis,
            options=options,
            key_generator=self.key_generator,
        )
