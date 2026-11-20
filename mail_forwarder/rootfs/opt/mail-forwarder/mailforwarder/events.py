"""A small in-memory activity log that the web interface shows next to the Supervisor log."""
import itertools
import logging
import threading
import time
from collections import deque

LOGGER = logging.getLogger("mail-forwarder")

LEVELS = {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}


class ActivityLog:
    """Keeps the newest events; every event is mirrored to the normal application log."""

    def __init__(self, capacity: int = 300):
        self._items: deque = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def add(self, level: str, message: str) -> None:
        LOGGER.log(LEVELS.get(level, logging.INFO), message)
        entry = {"id": next(self._ids), "time": time.time(), "level": level, "message": message}
        with self._lock:
            self._items.append(entry)

    def info(self, message: str) -> None:
        self.add("info", message)

    def warning(self, message: str) -> None:
        self.add("warning", message)

    def error(self, message: str) -> None:
        self.add("error", message)

    def recent(self, limit: int = 100) -> list:
        """Newest event first."""
        with self._lock:
            return list(reversed(self._items))[:limit]
