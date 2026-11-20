"""The part that listens on port 25: a deliberately small SMTP receiver.

It speaks just enough SMTP (RFC 5321) for other mail servers to hand over mail, and it does one
thing differently from a normal mail server: it checks every recipient *during* the conversation.
Unknown addresses are refused right there, so this app never accepts mail it cannot forward and
therefore never sends bounce messages to forged senders ("backscatter").
"""
import asyncio
import re
import ssl
from email.utils import formatdate
from typing import Callable, Optional

from . import settings
from .addresses import domain_of, extract_path, normalize_address
from .events import ActivityLog
from .inbox import Inbox, QueueFull
from .rewrite import count_headers
from .stats import Stats
from .tlsutil import TlsProvider

_MAIL_FROM = re.compile(r"^FROM:\s*(<[^>]*>|\S+)(.*)$", re.IGNORECASE)
_RCPT_TO = re.compile(r"^TO:\s*(<[^>]*>|\S+)(.*)$", re.IGNORECASE)
_UNSAFE_HELO = re.compile(r"[^A-Za-z0-9.\-:\[\]_]")
_SIZE_PARAMETER = re.compile(r"\bSIZE=(\d+)\b", re.IGNORECASE)

_QUIT = "quit"


class _Session:
    """One connection from another mail server."""

    def __init__(self, server: "SmtpServer", reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 peer: str):
        self.server = server
        self.reader = reader
        self.writer = writer
        self.peer = peer
        self.tls_active = False
        self.helo = ""
        self.bad_recipients = 0
        self._reset_transaction()
        self.commands = {
            "helo": self.cmd_helo, "ehlo": self.cmd_helo, "starttls": self.cmd_starttls,
            "mail": self.cmd_mail, "rcpt": self.cmd_rcpt, "data": self.cmd_data,
            "rset": self.cmd_rset, "noop": self.cmd_noop, "quit": self.cmd_quit, "vrfy": self.cmd_vrfy,
        }

    # ---- plumbing ----------------------------------------------------------------------------

    def _reset_transaction(self) -> None:
        self.sender: Optional[str] = None
        self.recipients: list = []

    async def reply(self, code: int, text: str, enhanced: str = "") -> None:
        prefix = f"{code} {enhanced} " if enhanced else f"{code} "
        self.writer.write(f"{prefix}{text}\r\n".encode())
        await self.writer.drain()

    async def read_line(self) -> Optional[bytes]:
        """One line from the client, or None when the connection is over (and the reason was sent)."""
        try:
            line = await asyncio.wait_for(self.reader.readline(), settings.IDLE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            await self.reply(421, "Timeout, closing the connection", "4.4.2")
            return None
        except (ValueError, asyncio.LimitOverrunError):
            await self.reply(500, "Line too long", "5.5.2")
            return None
        return line or None

    async def run(self) -> None:
        await self.reply(220, f"{self.server.hostname()} ESMTP Mail Forwarder")
        while True:
            line = await self.read_line()
            if line is None:
                return
            verb, _, argument = line.decode("utf-8", "replace").strip().partition(" ")
            handler = self.commands.get(verb.lower())
            if handler is None:
                await self.reply(502, "Command not implemented", "5.5.1")
            elif await handler(argument.strip()) == _QUIT:
                return

    # ---- commands ----------------------------------------------------------------------------

    async def cmd_helo(self, argument: str) -> None:
        if not argument:
            await self.reply(501, "Syntax: EHLO hostname", "5.5.4")
            return
        self.helo = _UNSAFE_HELO.sub("", argument)[:64] or "unknown"
        self._reset_transaction()
        lines = [f"{self.server.hostname()} Hello {self.helo}",
                 f"SIZE {settings.MAX_MESSAGE_BYTES}", "8BITMIME", "ENHANCEDSTATUSCODES"]
        if not self.tls_active and self.server.tls_context() is not None:
            lines.append("STARTTLS")
        for line in lines[:-1]:
            self.writer.write(f"250-{line}\r\n".encode())
        self.writer.write(f"250 {lines[-1]}\r\n".encode())
        await self.writer.drain()

    async def cmd_starttls(self, _argument: str) -> None:
        context = self.server.tls_context()
        if self.tls_active or context is None:
            await self.reply(502, "STARTTLS is not available", "5.5.1")
            return
        await self.reply(220, "Ready to start TLS", "2.0.0")
        await self.writer.start_tls(context)
        self.tls_active = True
        self.helo = ""
        self._reset_transaction()

    async def cmd_mail(self, argument: str) -> None:
        if not self.helo:
            await self.reply(503, "Say EHLO first", "5.5.1")
            return
        if self.sender is not None:
            await self.reply(503, "A mail transaction is already running", "5.5.1")
            return
        found = _MAIL_FROM.match(argument)
        if not found:
            await self.reply(501, "Syntax: MAIL FROM:<address>", "5.5.4")
            return
        size = _SIZE_PARAMETER.search(found.group(2))
        if size and int(size.group(1)) > settings.MAX_MESSAGE_BYTES:
            await self.reply(552, "Message too large", "5.3.4")
            return
        self.sender = extract_path(found.group(1))
        await self.reply(250, "Sender ok", "2.1.0")

    async def cmd_rcpt(self, argument: str) -> None:
        if self.sender is None:
            await self.reply(503, "Need MAIL FROM first", "5.5.1")
            return
        found = _RCPT_TO.match(argument)
        if not found:
            await self.reply(501, "Syntax: RCPT TO:<address>", "5.5.4")
            return
        address = normalize_address(extract_path(found.group(1)))
        if len(self.recipients) >= settings.MAX_RECIPIENTS:
            await self.reply(452, "Too many recipients", "4.5.3")
        elif address is not None and self.server.inbox.lookup(address) is not None:
            if address not in self.recipients:
                self.recipients.append(address)
            await self.reply(250, "Recipient ok", "2.1.5")
        else:
            await self.reject_recipient(address)

    async def reject_recipient(self, address: Optional[str]) -> None:
        self.server.stats.rejected()
        self.bad_recipients += 1
        if address is not None and not self.server.inbox.is_own_domain(domain_of(address)):
            await self.reply(550, "Relay access denied", "5.7.1")
        else:
            await self.reply(550, "No such user here", "5.1.1")
        if self.bad_recipients >= settings.MAX_BAD_RECIPIENTS:
            await self.reply(421, "Too many unknown recipients, goodbye", "4.7.0")
            self.writer.close()

    async def cmd_data(self, _argument: str) -> None:
        if not self.recipients:
            await self.reply(503, "No valid recipients", "5.5.1")
            return
        if not self.server.inbox.has_capacity():
            await self.reply(452, "Queue is full, try again later", "4.3.1")
            return
        await self.reply(354, "End data with <CR><LF>.<CR><LF>")
        raw = await self.read_message()
        if raw is None:
            return
        await self.finish_message(raw)

    async def read_message(self) -> Optional[bytes]:
        """The message with dot-stuffing removed and CRLF line ends; None if the client went away.
        A message that is too large is read to its end and then answered with an error."""
        chunks: list = []
        size = 0
        while True:
            line = await self.read_line()
            if line is None:
                return None
            if line.rstrip(b"\r\n") == b".":
                break
            if line.startswith(b"."):
                line = line[1:]
            line = line.rstrip(b"\r\n") + b"\r\n"
            size += len(line)
            if size <= settings.MAX_MESSAGE_BYTES:
                chunks.append(line)
        if size > settings.MAX_MESSAGE_BYTES:
            await self.reply(552, "Message too large", "5.3.4")
            self._reset_transaction()
            return None
        return b"".join(chunks)

    async def finish_message(self, raw: bytes) -> None:
        if count_headers(raw, "received") > settings.MAX_RECEIVED_HEADERS:
            await self.reply(554, "Too many hops, this looks like a mail loop", "5.4.6")
            self._reset_transaction()
            return
        protocol = "ESMTPS" if self.tls_active else "ESMTP"
        trace = (f"Received: from {self.helo} ([{self.peer}])\r\n\tby {self.server.hostname()} with {protocol};\r\n"
                 f"\t{formatdate()}\r\n").encode()
        try:
            jobs = self.server.inbox.accept(self.sender or "", self.recipients, trace + raw)
        except QueueFull:
            await self.reply(452, "Queue is full, try again later", "4.3.1")
        except OSError as error:
            self.server.events.error(f"Could not store a message: {error}")
            await self.reply(451, "Local error, try again later", "4.3.0")
        else:
            await self.reply(250, f"Queued as {','.join(job.id for job in jobs)}", "2.0.0")
        self._reset_transaction()

    async def cmd_rset(self, _argument: str) -> None:
        self._reset_transaction()
        await self.reply(250, "Ok", "2.0.0")

    async def cmd_noop(self, _argument: str) -> None:
        await self.reply(250, "Ok", "2.0.0")

    async def cmd_vrfy(self, _argument: str) -> None:
        await self.reply(252, "Cannot verify, but will try to deliver", "2.5.2")

    async def cmd_quit(self, _argument: str) -> str:
        await self.reply(221, "Bye", "2.0.0")
        return _QUIT


class SmtpServer:
    def __init__(self, inbox: Inbox, hostname: Callable[[], str], tls: TlsProvider, stats: Stats,
                 events: ActivityLog):
        self.inbox = inbox
        self.stats = stats
        self.events = events
        self._hostname = hostname
        self._tls = tls
        self._connections = 0
        self._server: Optional[asyncio.AbstractServer] = None

    def hostname(self) -> str:
        return self._hostname()

    def tls_context(self) -> Optional[ssl.SSLContext]:
        return self._tls.context_for(self._hostname())

    async def start(self, host: str, port: int) -> int:
        """Starts listening and returns the port (useful when port 0 was requested)."""
        self._server = await asyncio.start_server(self._handle, host, port, limit=settings.MAX_LINE_BYTES)
        return self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = (writer.get_extra_info("peername") or ("unknown",))[0]
        try:
            if self._connections >= settings.MAX_CONNECTIONS:
                writer.write(b"421 4.3.2 Too many connections, try again later\r\n")
                await writer.drain()
                return
            self._connections += 1
            try:
                self.stats.connection(peer)
                await _Session(self, reader, writer, peer).run()
            finally:
                self._connections -= 1
        except (ConnectionError, asyncio.TimeoutError, ssl.SSLError, OSError):
            pass  # the other side vanished or failed the TLS handshake; nothing to report
        finally:
            try:
                writer.close()
            except OSError:
                pass
