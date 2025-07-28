from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, ClassVar


from fastapi_redilimit.exception import HTTPRateLimitReached
from fastapi_redilimit.rate_limiter import (
    RateLimitResult,
    RedisRateLimiter,
    RateLimitStrategy,
)

if TYPE_CHECKING:
    from fastapi import Request
    import redis.asyncio
    from fastapi_redilimit.key_generators import AbstractKeyGenerator
    # from fastapi import


class _Redilimiter:
    '''
    Internal singleton class to hold the RedisRateLimiter instance.
    '''
    _rate_limiter: ClassVar[RedisRateLimiter | None] = None

    @classmethod
    def setup(cls, rate_limiter: RedisRateLimiter) -> "_Redilimiter":
        if cls._instance is None:
            cls._instance = _Redilimiter()
        cls._rate_limiter = rate_limiter
        return cls._instance

    @classmethod
    def get_rate_limiter(cls) -> RedisRateLimiter:
        if cls._rate_limiter is None:
            raise ValueError("Rate limiter has not been set up.")
        return cls._rate_limiter


def setup_rate_limiter(
    *,
    redis_connection: redis.asyncio.Redis,
    strategy: RateLimitStrategy = RateLimitStrategy.CLIENT,
    redis_key_prefix: str = "ratelimit",
    custom_key_generator: AbstractKeyGenerator | None = None,
) -> None:
    """
    Sets up the rate limiter with the provided Redis connection and configuration.

    Parameters
    ----------
    redis_connection : redis.asyncio.Redis
        _the async redis connection_
    strategy : RateLimitStrategy, optional
        _The strategy to use to identify an incoming request_,
        by default RateLimitStrategy.CLIENT

        - Options are:
            - `RateLimitStrategy.CLIENT`: Uses both the User
            Agent & IP address of the request, **reccommended**
            since IP address parsing depends on your backend.
            - `RateLimitStrategy.IP`: Uses only the IP address of the request
            - `RateLimitStrategy.USER_AGENT`: Uses only the User Agent of the request

    redis_key_prefix : str, optional
        _The redis key prefix to use to store and manipulate rate limit associated
        actions_, by default "ratelimit"
    custom_key_generator : AbstractKeyGenerator | None, optional
        _A custom key generator for uniquely identifying and generating
        the redis keys_, by default None
          - **Warning**: You most likely will not need this and reserve
          this for advanced use cases. If you do use this option
          ensure no key collisions can occur or you risk unexpected behavior
          occuring.

    ### Technical Details
    - This function creates a single instance of `RedisRateLimiter` and stores
    it in a plugin singleton. and when you call the `rate_limit` function, it will
    use this instance to create a limiter.
    """

    rate_limiter = RedisRateLimiter(
        redis_connection=redis_connection,
        strategy=strategy,
        redis_key_prefix=redis_key_prefix,
        custom_key_generator=custom_key_generator,
    )
    _Redilimiter.setup(rate_limiter)


def rate_limit(
    *,
    max_requests: int = 100,
    per_second: int = 60,
    per_hour: int = 0,
    auto_raise: bool = True,
) -> Callable[[Request], Awaitable[RateLimitResult]]:
    """
    Creates a rate limit dependency function that can be applied to FastAPI routes
    or routers.

    **Note**: You must call `setup_rate_limiter` before using this function

    Parameters
    ----------
    max_requests : int, optional
        _the maximum amount of allow requests in the time frame_, by default 100
    per_second : int, optional
        _the allowed requests per second_, by default 60
    per_hour : int, optional
        _the allowed requests per hour_, by default 0
    auto_raise : bool, optional
        _whether to raise `HTTPRateLimitReached` when the rate limit is reached_,
        by default True

    Returns
    -------
    Callable[[Request], Awaitable[RateLimitResult]]
        _The function that can be used via dependency injection_

    Raises
    ------
    HTTPRateLimitReached
        _When a request / client reaches the rate limit_
    """
    redilimiter = _Redilimiter.get_rate_limiter()

    limiter = redilimiter.create_limiter(
        max_requests=max_requests, window_hours=per_hour, window_seconds=per_second
    )

    async def _rate_limit_enforcer(request: Request) -> RateLimitResult:
        result = await limiter.check(request)
        if not result.allowed and auto_raise:
            raise HTTPRateLimitReached(result)

        return result

    return _rate_limit_enforcer
