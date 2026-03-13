from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    async def allow(self, key: str, limit: int, window_sec: int) -> bool:
        now = time.time()
        async with self._lock:
            bucket = self._buckets[key]
            while bucket and now - bucket[0] >= window_sec:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True
