"""What happens to a message once the SMTP server has received it completely."""
import threading
from typing import Callable, Optional

from . import settings
from .events import ActivityLog
from .rewrite import header_value
from .spool import Job, Spool
from .stats import Stats
from .store import ConfigStore, Route
from .testmail import TestTracker


class QueueFull(Exception):
    """The disk queue holds too many messages to take another one."""


class Inbox:
    def __init__(self, store: ConfigStore, spool: Spool, stats: Stats, events: ActivityLog,
                 tests: TestTracker, wake_worker: Callable[[], None]):
        self._store = store
        self._spool = spool
        self._stats = stats
        self._events = events
        self._tests = tests
        self._wake_worker = wake_worker
        self._lock = threading.Lock()

    def lookup(self, address: str) -> Optional[Route]:
        return self._store.routes().get(address)

    def is_own_domain(self, domain: str) -> bool:
        return domain in self._store.domain_names()

    def has_capacity(self) -> bool:
        return self._spool.counts()["queued"] < settings.MAX_QUEUE_ITEMS

    def accept(self, sender: str, recipients: list, raw: bytes) -> list:
        """Queues one job per real mailbox. ``recipients`` are addresses that passed ``lookup``."""
        by_target: dict = {}
        for address in recipients:
            route = self.lookup(address)
            if route is not None:
                by_target.setdefault(route.target, []).append(address)

        token = self._test_token(raw)
        jobs: list = []
        with self._lock:
            if not self.has_capacity():
                raise QueueFull()
            for target, aliases in by_target.items():
                jobs.append(self._spool.add(sender, target, aliases, raw, token))
        for job in jobs:
            self._events.info(f"Received a message for {', '.join(job.aliases)}; forwarding to {job.target}.")
            self._stats.received()
        if token:
            self._tests.mark(token, "arrived")
        self._wake_worker()
        return jobs

    def _test_token(self, raw: bytes) -> str:
        """The token of our own test message, or an empty string for everything else."""
        token = (header_value(raw, settings.TEST_HEADER) or "").strip()
        return token if token and self._tests.knows(token) else ""


def describe(job: Job) -> str:
    return f"{job.sender or 'unknown sender'} -> {', '.join(job.aliases)}"
