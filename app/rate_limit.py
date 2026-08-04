from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Protocol

from redis.exceptions import RedisError


class RateLimiter(Protocol):
    def allow(self, identity: str) -> bool:
        ...


class InMemoryRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, identity: str) -> bool:
        now = datetime.now(UTC).timestamp()
        q = self._hits[identity]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


class RedisRateLimiter:
    def __init__(self, limit_per_minute: int, redis_client) -> None:
        self.limit = limit_per_minute
        self.redis = redis_client

    def allow(self, identity: str) -> bool:
        current_minute = int(time.time() // 60)
        key = f"shortener:create:{identity}:{current_minute}"
        try:
            value = int(self.redis.incr(key))
            if value == 1:
                self.redis.expire(key, 120)
            return value <= self.limit
        except RedisError:
            # Fail closed for safety under Redis errors.
            return False
