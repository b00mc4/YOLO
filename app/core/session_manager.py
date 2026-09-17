import uuid
import time
import threading
from collections import deque

_DEFAULT_MAX_SESSIONS = 5
_GRACE_SECONDS = 30.0

class SessionManager:
    def __init__(self, max_sessions: int = _DEFAULT_MAX_SESSIONS):
        self.max_sessions = max_sessions
        self._sessions: dict[uuid.UUID, deque[str]] = {}
        self._graced: dict[str, float] = {}
        self._lock = threading.Lock()

    def _cleanup_graced(self) -> None:
        now = time.monotonic()
        expired = [sid for sid, exp in self._graced.items() if now >= exp]
        for sid in expired:
            del self._graced[sid]

    def add_session(self, user_id: uuid.UUID, session_id: str) -> None:
        with self._lock:
            if user_id not in self._sessions:
                self._sessions[user_id] = deque()
            sessions = self._sessions[user_id]
            if session_id in sessions:
                sessions.remove(session_id)
            sessions.append(session_id)
            while len(sessions) > self.max_sessions:
                sessions.popleft()

    def is_valid_session(self, user_id: uuid.UUID, session_id: str) -> bool:
        with self._lock:
            sessions = self._sessions.get(user_id)
            if sessions and session_id in sessions:
                return True
            self._cleanup_graced()
            return session_id in self._graced

    def remove_session_by_id(self, session_id: str) -> None:
        with self._lock:
            for user_id, sessions in list(self._sessions.items()):
                if session_id in sessions:
                    sessions.remove(session_id)
                    if not sessions:
                        del self._sessions[user_id]
                    break

    def remove_session_with_grace(self, session_id: str, grace_seconds: float = _GRACE_SECONDS) -> None:
        with self._lock:
            for user_id, sessions in list(self._sessions.items()):
                if session_id in sessions:
                    sessions.remove(session_id)
                    if not sessions:
                        del self._sessions[user_id]
                    break
            self._graced[session_id] = time.monotonic() + grace_seconds
            self._cleanup_graced()

    def remove_all_sessions(self, user_id: uuid.UUID) -> None:
        with self._lock:
            if user_id in self._sessions:
                del self._sessions[user_id]

session_manager = SessionManager(max_sessions=_DEFAULT_MAX_SESSIONS)
