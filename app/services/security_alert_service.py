from __future__ import annotations
from collections import OrderedDict
from time import monotonic


class AccountLocked(Exception):
    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Account locked")


class _LockState:
    __slots__ = ("fail_count", "locked_until", "current_lockout_seconds")

    def __init__(self) -> None:
        self.fail_count = 0
        self.locked_until = 0.0
        self.current_lockout_seconds = 0.0


class InMemorySingleWorkerAccountLocker:
    _FIRST_LOCKOUT_THRESHOLD = 5
    _LOCKOUT_STEP_SECONDS = 5.0
    _MAX_TRACKED_ACCOUNTS = 10_000

    def __init__(self) -> None:
        self._state: OrderedDict[str, _LockState] = OrderedDict()

    def check_locked(self, key: str) -> None:
        entry = self._state.get(key)
        if entry is None:
            return

        self._state.move_to_end(key)

        now = monotonic()
        if entry.locked_until > now:
            raise AccountLocked(retry_after_seconds=entry.locked_until - now)

    def register_failure(self, key: str) -> float | None:
        entry = self._state.get(key)

        if entry is None:
            if len(self._state) >= self._MAX_TRACKED_ACCOUNTS:
                self._state.popitem(last=False)
            entry = _LockState()
            self._state[key] = entry
        else:
            self._state.move_to_end(key)

        has_locked_before = entry.current_lockout_seconds > 0
        threshold = 1 if has_locked_before else self._FIRST_LOCKOUT_THRESHOLD

        entry.fail_count += 1
        if entry.fail_count >= threshold:
            entry.current_lockout_seconds += self._LOCKOUT_STEP_SECONDS
            entry.locked_until = monotonic() + entry.current_lockout_seconds
            entry.fail_count = 0
            return entry.current_lockout_seconds

        return None

    def reset(self, key: str) -> None:
        self._state.pop(key, None)


_account_locker = InMemorySingleWorkerAccountLocker()


def get_account_locker() -> InMemorySingleWorkerAccountLocker:
    return _account_locker