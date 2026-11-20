"""The background loop that works through the queue."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import settings
from .delivery import ATTENTION, PERMANENT, DeliveryError, Deliverer, classify
from .events import ActivityLog
from .spool import Job, Spool
from .stats import Stats
from .testmail import TestTracker

_PURGE_INTERVAL_SECONDS = 3600


class DeliveryWorker:
    def __init__(self, spool: Spool, deliverer: Deliverer, stats: Stats, events: ActivityLog,
                 tests: TestTracker):
        self._spool = spool
        self._deliverer = deliverer
        self._stats = stats
        self._events = events
        self._tests = tests
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._in_flight: set = set()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=settings.DELIVERY_THREADS, thread_name_prefix="delivery")
        self._thread = threading.Thread(target=self._loop, name="delivery-loop", daemon=True)

    def start(self) -> None:
        self._spool.clean_leftovers()
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def wake(self) -> None:
        self._wake.set()

    # ---- loop --------------------------------------------------------------------------------

    def _loop(self) -> None:
        last_purge = 0.0
        while not self._stopping.is_set():
            if time.time() - last_purge > _PURGE_INTERVAL_SECONDS:
                self._spool.purge_old_failures(settings.FAILED_RETENTION_DAYS)
                last_purge = time.time()
            for job in self._spool.due():
                with self._lock:
                    if job.id in self._in_flight:
                        continue
                    self._in_flight.add(job.id)
                self._pool.submit(self._process, job)
            self._wake.wait(settings.SPOOL_SCAN_SECONDS)
            self._wake.clear()

    def _process(self, job: Job) -> None:
        try:
            self._deliverer.forward(job, self._spool.read_raw(job))
        except FileNotFoundError:
            self._spool.discard(job.id)
        except Exception as error:  # noqa: BLE001 - classified below
            self._handle_failure(job, classify(error))
        else:
            self._spool.complete(job)
            self._stats.forwarded()
            self._events.info(f"Forwarded a message for {', '.join(job.aliases)} to {job.target}.",
                              "forwarded", aliases=", ".join(job.aliases), target=job.target)
            if job.test_token:
                self._tests.mark(job.test_token, "forwarded")
        finally:
            with self._lock:
                self._in_flight.discard(job.id)
            self._wake.set()

    def _handle_failure(self, job: Job, error: DeliveryError) -> None:
        job.attempts += 1
        job.last_error = str(error)
        job.error_code, job.error_params = error.code, error.params
        job.needs_attention = error.kind == ATTENTION
        where = f"{', '.join(job.aliases)} -> {job.target}"
        details = {"aliases": ", ".join(job.aliases), "target": job.target,
                   "error_code": error.code, "error_params": error.params}
        if error.kind == PERMANENT or job.attempts > len(settings.RETRY_DELAYS_MINUTES):
            self._spool.park(job)
            self._stats.gave_up()
            self._events.error(f"Gave up on a message ({where}): {error}", "gave_up", **details)
            if job.test_token:
                self._tests.fail(job.test_token, error)
            return
        minutes = settings.ATTENTION_RETRY_MINUTES if error.kind == ATTENTION \
            else settings.RETRY_DELAYS_MINUTES[job.attempts - 1]
        job.next_attempt = time.time() + minutes * 60
        self._spool.save(job)
        prefix = "Needs your attention" if error.kind == ATTENTION else "Could not forward yet"
        self._events.warning(f"{prefix} ({where}): {error}. Next try in {minutes} min.",
                             "attention" if error.kind == ATTENTION else "retry_later", minutes=minutes, **details)
        if job.test_token and error.kind == ATTENTION:
            self._tests.fail(job.test_token, error)
