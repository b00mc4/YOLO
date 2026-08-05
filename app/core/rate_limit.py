from __future__ import annotations
from collections import deque
from time import monotonic


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Rate limit exceeded")


class InMemorySingleWorkerRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str, limit: int, window_seconds: float) -> None:
        now = monotonic()
        hits = self._hits.setdefault(key, deque())

        while hits and now - hits[0] >= window_seconds:
            hits.popleft()

        if len(hits) >= limit:
            raise RateLimitExceeded(retry_after_seconds=window_seconds - (now - hits[0]))

        hits.append(now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


_rate_limiter = InMemorySingleWorkerRateLimiter()


def get_rate_limiter() -> InMemorySingleWorkerRateLimiter:
    return _rate_limiter