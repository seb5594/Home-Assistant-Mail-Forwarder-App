"""Counters shown on the overview page, kept in the persistent state.

Port 25 on the internet is probed by scanners all day. Counting those hits must not wear out an
SD card, so noisy counters live in memory and are written at most every few minutes (and on exit).
"""
import ipaddress
import threading
import time

from .state import State

_FLUSH_INTERVAL_SECONDS = 300
_NOISY = ("rejected", "last_connection", "last_outside_connection")


def _is_outside(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


class Stats:
    def __init__(self, state: State):
        self._state = state
        self._lock = threading.Lock()
        self._noisy = {key: state.get(key) for key in _NOISY}
        self._noisy["rejected"] = int(self._noisy["rejected"] or 0)
        self._last_flush = time.time()
        self._first_outside_saved = self._noisy["last_outside_connection"] is not None

    # ---- noisy counters (memory first) -------------------------------------------------------

    def connection(self, address: str) -> None:
        """Remembers the latest connection. One from a public address proves that the port
        forwarding of your router works, so the first of those is saved immediately."""
        entry = {"address": address, "time": time.time(), "outside": _is_outside(address)}
        with self._lock:
            self._noisy["last_connection"] = entry
            first_outside = entry["outside"] and not self._first_outside_saved
            if entry["outside"]:
                self._noisy["last_outside_connection"] = entry
                self._first_outside_saved = True
        self._flush(force=first_outside)

    def rejected(self) -> None:
        with self._lock:
            self._noisy["rejected"] += 1
        self._flush()

    def _flush(self, force: bool = False) -> None:
        with self._lock:
            if not force and time.time() - self._last_flush < _FLUSH_INTERVAL_SECONDS:
                return
            self._last_flush = time.time()
            values = dict(self._noisy)
        self._state.update(values)

    def flush(self) -> None:
        self._flush(force=True)

    # ---- rare events (saved immediately) -----------------------------------------------------

    def received(self) -> None:
        self._state.increment("received")

    def forwarded(self) -> None:
        self._state.update({"forwarded": int(self._state.get("forwarded", 0)) + 1,
                            "last_forwarded": time.time()})

    def gave_up(self) -> None:
        self._state.increment("gave_up")

    def snapshot(self) -> dict:
        data = self._state.snapshot()
        with self._lock:
            data.update(self._noisy)
        return {key: data.get(key) for key in (
            "received", "forwarded", "rejected", "gave_up", "last_forwarded",
            "last_connection", "last_outside_connection")}
