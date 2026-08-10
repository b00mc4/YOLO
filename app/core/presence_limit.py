from __future__ import annotations


class PresenceConnectionLimitExceeded(Exception):
    def __init__(self, max_connections: int):
        self.max_connections = max_connections
        super().__init__("Too many concurrent presence connections for this user")