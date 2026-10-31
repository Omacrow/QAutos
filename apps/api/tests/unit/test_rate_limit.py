from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from sqa.core.rate_limit import RateLimiter


async def test_blocks_after_limit() -> None:
    limiter = RateLimiter(FakeAsyncRedis(), limit=3, window_seconds=60)
    results = [await limiter.hit("user:a") for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert 0 < results[-1].retry_after <= 60


async def test_keys_are_independent() -> None:
    limiter = RateLimiter(FakeAsyncRedis(), limit=1, window_seconds=60)
    assert (await limiter.hit("user:a")).allowed
    assert (await limiter.hit("user:b")).allowed
    assert not (await limiter.hit("user:a")).allowed


async def test_fails_open_when_redis_is_down() -> None:
    class BrokenRedis(FakeAsyncRedis):
        def pipeline(self, *args: object, **kwargs: object) -> object:
            raise RedisConnectionError("down")

    limiter = RateLimiter(BrokenRedis(), limit=1, window_seconds=60)
    assert (await limiter.hit("user:a")).allowed
