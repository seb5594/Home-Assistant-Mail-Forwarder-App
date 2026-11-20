"""Small facts the application remembers between restarts (counters, last public IP, ...)."""
import threading
from pathlib import Path
from typing import Any

from .jsonfile import read_json, write_json


class State:
    """A thread-safe dictionary that saves itself on every change."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._data: dict = read_json(path, {})

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            write_json(self._path, self._data)

    def increment(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._data[key] = int(self._data.get(key, 0)) + amount
            write_json(self._path, self._data)

    def update(self, values: dict) -> None:
        with self._lock:
            self._data.update(values)
            write_json(self._path, self._data)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._data)
