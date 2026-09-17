import asyncio
import base64
import binascii
from collections import defaultdict, deque
import secrets
import time

from .config import Settings


def basic_auth_valid(header: str | None, settings: Settings) -> bool:
    if not settings.access_protected:
        return True
    if not header:
        return False
    try:
        scheme, encoded = header.split(" ", 1)
        if scheme.lower() != "basic":
            return False
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    return secrets.compare_digest(username, settings.app_access_username) and (
        secrets.compare_digest(password, settings.app_access_password)
    )


class WriteRateLimiter:
    """Single-process sliding-window limiter for state-changing API requests."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, key: str, *, now: float | None = None) -> tuple[bool, int]:
        timestamp = time.monotonic() if now is None else now
        cutoff = timestamp - self.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (timestamp - events[0])))
                return False, retry_after
            events.append(timestamp)
            if not events:
                self._events.pop(key, None)
        return True, 0
