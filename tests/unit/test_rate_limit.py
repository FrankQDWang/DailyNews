from libs.core.rate_limit import SlidingWindowRateLimiter


async def test_sliding_window_rate_limiter() -> None:
    limiter = SlidingWindowRateLimiter()
    key = 'k'
    assert await limiter.allow(key, limit=2, window_sec=60) is True
    assert await limiter.allow(key, limit=2, window_sec=60) is True
    assert await limiter.allow(key, limit=2, window_sec=60) is False
