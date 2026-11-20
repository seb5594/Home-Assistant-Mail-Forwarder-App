"""The queue on disk: one raw message file plus one small JSON file per mailbox it goes to.

A message only counts as queued once its JSON file exists, and that file is written last. A crash
while receiving therefore never leaves a half-written entry that the worker would try to send.
"""
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from .jsonfile import read_json, write_json


@dataclass
class Job:
    id: str
    sender: str
    target: str
    aliases: list
    received_at: float
    size: int
    attempts: int = 0
    next_attempt: float = 0.0
    last_error: str = ""
    needs_attention: bool = False
    test_token: str = ""
    failed_at: float = 0.0
    extra: dict = field(default_factory=dict)

    def public(self) -> dict:
        data = asdict(self)
        data.pop("extra", None)
        return data


class Spool:
    def __init__(self, queue_dir: Path, failed_dir: Path):
        self._queue = queue_dir
        self._failed = failed_dir
        self._lock = threading.Lock()
        queue_dir.mkdir(parents=True, exist_ok=True)
        failed_dir.mkdir(parents=True, exist_ok=True)

    # ---- writing -----------------------------------------------------------------------------

    def add(self, sender: str, target: str, aliases: list, raw: bytes, test_token: str = "") -> Job:
        job = Job(id=uuid.uuid4().hex[:12], sender=sender, target=target, aliases=sorted(aliases),
                  received_at=time.time(), size=len(raw), test_token=test_token)
        with self._lock:
            self._write_raw(self._queue / f"{job.id}.eml", raw)
            write_json(self._queue / f"{job.id}.json", asdict(job), private=True)
        return job

    @staticmethod
    def _write_raw(path: Path, raw: bytes) -> None:
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def save(self, job: Job) -> None:
        with self._lock:
            if (self._queue / f"{job.id}.json").exists():
                write_json(self._queue / f"{job.id}.json", asdict(job), private=True)

    # ---- reading -----------------------------------------------------------------------------

    @staticmethod
    def _load(path: Path) -> Optional[Job]:
        data = read_json(path, None)
        if not isinstance(data, dict):
            return None
        try:
            return Job(**data)
        except TypeError:
            return None

    def _jobs(self, folder: Path) -> list:
        jobs = (self._load(path) for path in sorted(folder.glob("*.json")))
        return [job for job in jobs if job is not None]

    def queued(self) -> list:
        return self._jobs(self._queue)

    def failed(self) -> list:
        return self._jobs(self._failed)

    def due(self, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        return [job for job in self.queued() if job.next_attempt <= now]

    def read_raw(self, job: Job) -> bytes:
        for folder in (self._queue, self._failed):
            path = folder / f"{job.id}.eml"
            if path.exists():
                return path.read_bytes()
        raise FileNotFoundError(job.id)

    def counts(self) -> dict:
        return {"queued": len(list(self._queue.glob("*.json"))),
                "failed": len(list(self._failed.glob("*.json")))}

    def queue_bytes(self) -> int:
        return sum(path.stat().st_size for path in self._queue.glob("*.eml"))

    # ---- state changes -----------------------------------------------------------------------

    def complete(self, job: Job) -> None:
        """The message was delivered; nothing of it is kept."""
        with self._lock:
            for suffix in (".json", ".eml"):
                (self._queue / f"{job.id}{suffix}").unlink(missing_ok=True)

    def park(self, job: Job) -> None:
        """Moves a message that cannot be delivered into the failed folder."""
        job.failed_at = time.time()
        with self._lock:
            write_json(self._failed / f"{job.id}.json", asdict(job), private=True)
            raw = self._queue / f"{job.id}.eml"
            if raw.exists():
                os.replace(raw, self._failed / f"{job.id}.eml")
            (self._queue / f"{job.id}.json").unlink(missing_ok=True)

    def requeue(self, job_id: str) -> bool:
        """Puts a parked message back into the queue for another round of attempts."""
        with self._lock:
            job = self._load(self._failed / f"{job_id}.json")
            if job is None or not (self._failed / f"{job_id}.eml").exists():
                return False
            job.attempts, job.next_attempt, job.failed_at = 0, 0.0, 0.0
            os.replace(self._failed / f"{job_id}.eml", self._queue / f"{job_id}.eml")
            write_json(self._queue / f"{job_id}.json", asdict(job), private=True)
            (self._failed / f"{job_id}.json").unlink(missing_ok=True)
            return True

    def retry_now(self, job_id: str) -> bool:
        with self._lock:
            job = self._load(self._queue / f"{job_id}.json")
            if job is None:
                return False
            job.next_attempt = 0.0
            write_json(self._queue / f"{job_id}.json", asdict(job), private=True)
            return True

    def discard(self, job_id: str) -> bool:
        """Deletes a message from the queue or from the failed folder."""
        removed = False
        with self._lock:
            for folder in (self._queue, self._failed):
                for suffix in (".json", ".eml"):
                    path = folder / f"{job_id}{suffix}"
                    if path.exists():
                        path.unlink()
                        removed = True
        return removed

    def purge_old_failures(self, retention_days: int) -> int:
        cutoff = time.time() - retention_days * 86400
        old = [job for job in self.failed() if job.failed_at and job.failed_at < cutoff]
        for job in old:
            self.discard(job.id)
        return len(old)

    def clean_leftovers(self) -> None:
        """Removes raw files without a JSON file (a crash while receiving) and temporary files."""
        with self._lock:
            for path in self._queue.glob("*.tmp"):
                path.unlink(missing_ok=True)
            for path in self._queue.glob("*.eml"):
                if not path.with_suffix(".json").exists():
                    path.unlink(missing_ok=True)
