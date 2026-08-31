import uuid
import threading
from collections import deque

class SessionManager:
    def __init__(self, max_sessions: int = 5):
        self.max_sessions = max_sessions
        self._sessions: dict[uuid.UUID, deque[str]] = {}
        self._lock = threading.Lock()

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
            if not sessions:
                return False
            return session_id in sessions

    def remove_session_by_id(self, session_id: str) -> None:
        with self._lock:
            for user_id, sessions in list(self._sessions.items()):
                if session_id in sessions:
                    sessions.remove(session_id)
                    if not sessions:
                        del self._sessions[user_id]
                    break

    def remove_all_sessions(self, user_id: uuid.UUID) -> None:
        with self._lock:
            if user_id in self._sessions:
                del self._sessions[user_id]

session_manager = SessionManager(max_sessions=5)
