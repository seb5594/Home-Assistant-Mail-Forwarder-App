"""Tracks the progress of the 'send test mail' button across the three hops it proves:

    sent       the sending service (or the direct connection) accepted the test message
    arrived    the message came back to this app through the internet, so DNS, router and port work
    forwarded  the app handed it on to the real mailbox
"""
import secrets
import threading
import time
from typing import Optional

from . import settings

STEPS = ("sent", "arrived", "forwarded")


class TestTracker:
    __test__ = False  # not a test case for pytest

    def __init__(self):
        self._lock = threading.Lock()
        self._current: Optional[dict] = None

    def start(self, alias: str) -> str:
        token = secrets.token_hex(8)
        with self._lock:
            self._current = {"token": token, "alias": alias, "started": time.time(),
                             "steps": {step: None for step in STEPS}, "error": ""}
        return token

    def can_start(self) -> bool:
        """A new test may start when none is running (a finished or timed-out one is replaced)."""
        current = self.snapshot()
        return current is None or current["status"] != "running"

    def knows(self, token: str) -> bool:
        with self._lock:
            return bool(self._current and secrets.compare_digest(self._current["token"], token))

    def mark(self, token: str, step: str) -> None:
        with self._lock:
            if self._current and self._current["token"] == token:
                self._current["steps"][step] = time.time()

    def fail(self, token: str, message: str) -> None:
        with self._lock:
            if self._current and self._current["token"] == token:
                self._current["error"] = message

    def snapshot(self) -> Optional[dict]:
        with self._lock:
            if self._current is None:
                return None
            data = {**self._current, "steps": dict(self._current["steps"])}
        if data["steps"]["forwarded"]:
            data["status"] = "ok"
        elif data["error"]:
            data["status"] = "failed"
        elif time.time() - data["started"] > settings.TEST_MAIL_TIMEOUT_SECONDS:
            data["status"] = "timeout"
        else:
            data["status"] = "running"
        data.pop("token")
        return data
