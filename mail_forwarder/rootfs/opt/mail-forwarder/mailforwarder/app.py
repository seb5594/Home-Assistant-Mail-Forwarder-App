"""Builds all parts of the application and starts and stops them together."""
import asyncio
import logging
import signal
from pathlib import Path
from typing import Optional

from . import settings
from .ddns import DynamicDns
from .delivery import Deliverer
from .diagnostics import Diagnostics
from .events import ActivityLog
from .inbox import Inbox
from .smtp_server import SmtpServer
from .spool import Spool
from .state import State
from .stats import Stats
from .store import ConfigStore
from .testmail import TestTracker
from .tlsutil import TlsProvider
from .web import WebServer
from .worker import DeliveryWorker


class Application:
    def __init__(self, data_dir: Path = settings.DATA_DIR):
        self.events = ActivityLog()
        self.store = ConfigStore(data_dir / "forwarder.json")
        self.state = State(data_dir / "state.json")
        self.stats = Stats(self.state)
        self.spool = Spool(data_dir / "spool", data_dir / "failed")
        self.tests = TestTracker()
        self.deliverer = Deliverer(self.store, self.store.greeting_host)
        self.worker = DeliveryWorker(self.spool, self.deliverer, self.stats, self.events, self.tests)
        self.inbox = Inbox(self.store, self.spool, self.stats, self.events, self.tests, self.worker.wake)
        self.tls = TlsProvider(data_dir / "tls", self.events)
        self.smtp = SmtpServer(self.inbox, self.store.greeting_host, self.tls, self.stats, self.events)
        self.diagnostics = Diagnostics(self.store, self.stats, self.tests, self.deliverer)
        self.ddns = DynamicDns(self.store, self.state, self.events)
        self.web = WebServer(self)
        self.smtp_port: Optional[int] = None
        self.web_port: Optional[int] = None

    async def start(self, smtp_bind: str = settings.SMTP_BIND, smtp_port: int = settings.SMTP_PORT,
                    web_bind: str = settings.WEB_BIND, web_port: int = settings.WEB_PORT,
                    background_checks: bool = True) -> None:
        self.smtp_port = await self.smtp.start(smtp_bind, smtp_port)
        self.web_port = self.web.start(web_bind, web_port)
        self.worker.start()
        self.ddns.start()
        if background_checks:
            self.diagnostics.run_in_background()
        self.events.info(f"Ready: receiving mail on port {self.smtp_port}, web interface on port {self.web_port}.")

    async def stop(self) -> None:
        await self.smtp.stop()
        self.web.stop()
        self.worker.stop()
        self.ddns.stop()
        self.stats.flush()


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format="[%(levelname)s] %(message)s")


async def run_forever(application: Application) -> None:
    """Runs until the container is asked to stop."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    await application.start()
    await stop.wait()
    await application.stop()
