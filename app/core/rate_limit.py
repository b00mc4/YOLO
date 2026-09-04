from __future__ import annotations
from collections import OrderedDict, deque
from time import monotonic

PASSWORD_REAUTH_LIMIT = 5
PASSWORD_REAUTH_WINDOW_SECONDS = 15 * 60

class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Rate limit exceeded")


class InMemorySingleWorkerRateLimiter:
    _MAX_TRACKED_KEYS = 10_000

    def __init__(self) -> None:
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()

    def check(self, key: str, limit: int, window_seconds: float) -> None:
        now = monotonic()
        hits = self._hits.get(key)

        if hits is None:
            if len(self._hits) >= self._MAX_TRACKED_KEYS:
                self._hits.popitem(last=False)
            hits = deque()
            self._hits[key] = hits
        else:
            self._hits.move_to_end(key)

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

def password_reauth_key(user_id) -> str:
    return f"password_reauth:{user_id}"