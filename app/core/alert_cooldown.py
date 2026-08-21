from __future__ import annotations
from collections import OrderedDict
from time import monotonic


class InMemorySingleWorkerCooldown:
    _MAX_TRACKED_KEYS = 10_000

    def __init__(self) -> None:
        self._last_hit: OrderedDict[str, float] = OrderedDict()

    def allow(self, key: str, cooldown_seconds: float) -> bool:
        now = monotonic()
        last_hit_at = self._last_hit.get(key)

        if last_hit_at is None:
            if len(self._last_hit) >= self._MAX_TRACKED_KEYS:
                self._last_hit.popitem(last=False)
            self._last_hit[key] = now
            return True

        self._last_hit.move_to_end(key)
        within_cooldown = now - last_hit_at < cooldown_seconds
        self._last_hit[key] = now

        return not within_cooldown

    def reset(self, key: str) -> None:
        self._last_hit.pop(key, None)


_alert_cooldown = InMemorySingleWorkerCooldown()


def get_alert_cooldown() -> InMemorySingleWorkerCooldown:
    return _alert_cooldown