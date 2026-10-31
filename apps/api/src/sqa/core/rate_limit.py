import time
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

from sqa.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after: int


class RateLimiter:
    """Fixed-window counter in Redis.

    Fails open if Redis is unavailable: an outage of the limiter should not
    take the API down. The failure is logged so it is visible.
    """

    def __init__(self, redis: Redis, *, limit: int, window_seconds: int) -> None:
        self._redis = redis
        self._limit = limit
        self._window = window_seconds

    async def hit(self, key: str) -> RateLimitResult:
        window_start = int(time.time()) // self._window
        redis_key = f"rl:{key}:{window_start}"
        try:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, self._window)
                count, _ = await pipe.execute()
        except RedisError:
            log.warning("rate_limiter_unavailable")
            return RateLimitResult(allowed=True, retry_after=0)

        if int(count) > self._limit:
            retry_after = self._window - int(time.time()) % self._window
            return RateLimitResult(allowed=False, retry_after=retry_after)
        return RateLimitResult(allowed=True, retry_after=0)
