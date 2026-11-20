"""Shared helpers for the tests: the app wired up on free ports and a pretend sending service."""
import asyncio
import base64
import json
import os
import smtplib
import socketserver
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# Inside the image the code lives in /opt/mail-forwarder; in a checkout it is in the app folder.
CODE_DIR = Path(os.environ.get("MF_CODE_DIR") or
                Path(__file__).resolve().parents[2] / "mail_forwarder/rootfs/opt/mail-forwarder")
sys.path.insert(0, str(CODE_DIR))
os.environ.setdefault("MF_WEB_ROOT", str(CODE_DIR / "web"))

from mailforwarder.app import Application  # noqa: E402


def wait_for(condition, timeout: float = 10.0, interval: float = 0.05):
    """Polls until ``condition()`` is truthy and returns its value; fails the test on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("Timed out waiting for a condition")


class FakeRelay:
    """A tiny SMTP server that behaves like a sending service.

    Messages for the domains in ``loop_back`` are handed to ``loop_back_to`` (host, port), which
    imitates the internet carrying a test message back to the app.
    """

    def __init__(self, username: str = "user", password: str = "secret", refuse_recipients: tuple = ()):
        self.credentials = (username, password)
        self.refuse_recipients = refuse_recipients
        self.messages: list = []
        self.logins: list = []
        self.loop_back_domains: tuple = ()
        self.loop_back_to: tuple = ("127.0.0.1", 0)
        relay = self

        class Handler(socketserver.StreamRequestHandler):
            def reply(self, text: str) -> None:
                self.wfile.write(text.encode() + b"\r\n")

            def handle(self) -> None:
                self.reply("220 fake-relay ESMTP")
                sender, recipients = "", []
                while True:
                    line = self.rfile.readline().decode().strip()
                    if not line:
                        return
                    verb = line.split(" ", 1)[0].upper()
                    if verb == "EHLO":
                        self.wfile.write(b"250-fake-relay\r\n250-8BITMIME\r\n250 AUTH PLAIN\r\n")
                    elif verb == "AUTH":
                        _, user, password = base64.b64decode(line.split()[-1]).decode().split("\0")
                        relay.logins.append((user, password))
                        self.reply("235 2.7.0 Accepted" if (user, password) == relay.credentials
                                   else "535 5.7.8 Authentication failed")
                    elif verb == "MAIL":
                        sender = line.split("<", 1)[1].split(">", 1)[0]
                        self.reply("250 OK")
                    elif verb == "RCPT":
                        recipient = line.split("<", 1)[1].split(">", 1)[0]
                        if recipient in relay.refuse_recipients:
                            self.reply("550 5.1.1 No such mailbox")
                        else:
                            recipients.append(recipient)
                            self.reply("250 OK")
                    elif verb == "DATA":
                        self.reply("354 Go ahead")
                        lines = []
                        while (data_line := self.rfile.readline()) != b".\r\n":
                            lines.append(data_line[1:] if data_line.startswith(b"..") else data_line)
                        relay.accept(sender, recipients, b"".join(lines))
                        self.reply("250 2.0.0 Queued")
                    elif verb == "QUIT":
                        self.reply("221 Bye")
                        return
                    else:
                        self.reply("250 OK")

        class Server(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        self._server = Server(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def accept(self, sender: str, recipients: list, data: bytes) -> None:
        self.messages.append({"sender": sender, "recipients": recipients, "data": data})
        for recipient in recipients:
            if recipient.rpartition("@")[2] in self.loop_back_domains:
                with smtplib.SMTP(*self.loop_back_to, local_hostname="sender.example") as client:
                    client.sendmail(sender, [recipient], data)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class Harness:
    """The complete application in a temporary folder, listening on free local ports."""

    def __init__(self, config: dict = None):
        self._folder = tempfile.TemporaryDirectory()
        self.app = Application(Path(self._folder.name))
        if config:
            self.app.store.replace(config)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(
            self.app.start("127.0.0.1", 0, "127.0.0.1", 0, background_checks=False), self._loop).result(10)
        self.smtp_port, self.web_port = self.app.smtp_port, self.app.web_port

    def close(self) -> None:
        asyncio.run_coroutine_threadsafe(self.app.stop(), self._loop).result(10)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._folder.cleanup()

    # ---- helpers -----------------------------------------------------------------------------

    def send(self, sender: str, recipients: list, body: bytes) -> dict:
        """Delivers a message to the receiver like another mail server would."""
        with smtplib.SMTP("127.0.0.1", self.smtp_port, local_hostname="sender.example") as client:
            return client.sendmail(sender, recipients, body)

    def api(self, method: str, path: str, body: dict = None) -> tuple:
        """(status, parsed JSON) of a call to the web API."""
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"http://127.0.0.1:{self.web_port}{path}", data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")


def sample_config(relay_port: int, **delivery) -> dict:
    """A complete configuration: one domain, one person with one address, a relay on ``relay_port``."""
    return {
        "domains": [{"name": "example.test", "kind": "own", "mail_host": "mail.example.test"}],
        "people": [{"name": "Anna", "targets": ["anna@mailbox.test"], "enabled": True,
                    "addresses": [{"local": "info", "domain": "example.test"}]}],
        "delivery": {"mode": "relay", "sender_address": "forward@example.test", "rewrite_from": True,
                     "relay": {"preset": "custom", "host": "127.0.0.1", "port": relay_port, "security": "none",
                               "username": "user", "password": "secret"}, **delivery},
    }
