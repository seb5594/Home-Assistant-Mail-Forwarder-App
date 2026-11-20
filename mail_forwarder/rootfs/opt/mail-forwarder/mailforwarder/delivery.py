"""Sending a message on its way: through a mail service ("relay") or straight to the target server.

Every failure is sorted into one of three kinds, because each one needs a different reaction:

``temporary``   the other side is busy or unreachable; try again later with growing pauses
``attention``   a setting is wrong (login, sender address); keep the message and retry slowly,
                so it goes out by itself once the owner has fixed the setting
``permanent``   the other side refused the recipient for good; park the message
"""
import smtplib
import socket
import ssl
from email import policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Callable

from . import dns, settings
from .addresses import domain_of, normalize_address
from .rewrite import ForwardPlan, build_forward_message
from .spool import Job
from .store import ConfigStore

TEMPORARY, ATTENTION, PERMANENT = "temporary", "attention", "permanent"
_DIRECT_PORT = 25
_MAX_DIRECT_HOSTS = 4


class DeliveryError(Exception):
    def __init__(self, message: str, kind: str = TEMPORARY):
        super().__init__(message)
        self.kind = kind


def _response(error: smtplib.SMTPResponseException) -> str:
    text = error.smtp_error.decode("utf-8", "replace") if isinstance(error.smtp_error, bytes) else str(error.smtp_error)
    return f"{error.smtp_code} {text}".strip()[:300]


def classify(error: Exception) -> DeliveryError:
    """Turns whatever smtplib or the socket layer raised into a DeliveryError."""
    if isinstance(error, DeliveryError):
        return error
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return DeliveryError("The sending service rejected the login: " + _response(error), ATTENTION)
    if isinstance(error, smtplib.SMTPSenderRefused):
        return DeliveryError("The sending service does not accept the sender address: " + _response(error), ATTENTION)
    if isinstance(error, smtplib.SMTPNotSupportedError):
        return DeliveryError("The server does not offer a required feature: " + str(error), ATTENTION)
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        refusals = "; ".join(f"{who}: {code} {text.decode('utf-8', 'replace')}"
                             for who, (code, text) in error.recipients.items())
        kind = PERMANENT if all(code >= 500 for code, _ in error.recipients.values()) else TEMPORARY
        return DeliveryError("The recipient was refused: " + refusals[:300], kind)
    if isinstance(error, smtplib.SMTPResponseException):
        return DeliveryError(_response(error), PERMANENT if error.smtp_code >= 500 else TEMPORARY)
    if isinstance(error, (ssl.SSLError, smtplib.SMTPException, socket.timeout, OSError)):
        return DeliveryError(f"{type(error).__name__}: {error}", TEMPORARY)
    return DeliveryError(f"Unexpected error: {error}", TEMPORARY)


class Deliverer:
    def __init__(self, store: ConfigStore, hostname: Callable[[], str]):
        self._store = store
        self._hostname = hostname

    # ---- public entry points -----------------------------------------------------------------

    def forward(self, job: Job, raw: bytes) -> None:
        """Sends the queued message to the real mailbox."""
        config = self._store.get()["delivery"]
        alias_domain = domain_of(job.aliases[0])
        envelope_sender = self._envelope_sender(config, alias_domain)
        plan = ForwardPlan(alias=", ".join(job.aliases), from_address=envelope_sender,
                           rewrite_sender=config["rewrite_from"])
        self._send(config, envelope_sender, job.target, build_forward_message(raw, plan))

    def send_test(self, alias: str, token: str) -> None:
        """Sends a test message to ``alias`` the same way real mail leaves this app."""
        config = self._store.get()["delivery"]
        envelope_sender = self._envelope_sender(config, domain_of(alias))
        message = EmailMessage()
        message["From"] = formataddr(("Mail Forwarder test", envelope_sender))
        message["To"] = alias
        message["Subject"] = "Mail Forwarder test message"
        message["Date"] = formatdate(usegmt=True)
        message["Message-ID"] = make_msgid(domain=domain_of(envelope_sender))
        message[settings.TEST_HEADER] = token
        message.set_content(
            "This message was sent by the test button of your Mail Forwarder app.\n\n"
            "It travelled out through your sending service, back in through the internet to your\n"
            "Home Assistant, and on to your real mailbox. If you can read it, forwarding works.\n")
        self._send(config, envelope_sender, alias, message.as_bytes(policy=policy.SMTP))

    def test_login(self) -> tuple:
        """(ok, detail) of connecting and logging in to the sending service, without sending."""
        config = self._store.get()["delivery"]
        if config["mode"] != "relay":
            return False, "Direct sending does not use a login."
        if not config["relay"]["host"]:
            return False, "Choose a sending service first."
        try:
            connection = self._connect_relay(config["relay"])
            connection.quit()
        except Exception as error:  # noqa: BLE001 - every failure is explained to the user
            return False, str(classify(error))
        return True, f"Connected to {config['relay']['host']} and logged in."

    # ---- sender address ----------------------------------------------------------------------

    @staticmethod
    def _envelope_sender(config: dict, alias_domain: str) -> str:
        if config["mode"] == "direct":
            return f"forwarder@{alias_domain}"
        sender = config["sender_address"] or normalize_address(config["relay"]["username"]) or ""
        if not sender:
            raise DeliveryError("No sender address is set. Open the Sending page and fill in "
                                "'Sender address'.", ATTENTION)
        return sender

    # ---- transport ---------------------------------------------------------------------------

    def _send(self, config: dict, sender: str, recipient: str, data: bytes) -> None:
        try:
            if config["mode"] == "relay":
                self._send_via_relay(config["relay"], sender, recipient, data)
            else:
                self._send_direct(sender, recipient, data)
        except Exception as error:  # noqa: BLE001 - classified and re-raised
            raise classify(error) from error

    def _connect_relay(self, relay: dict) -> smtplib.SMTP:
        if not relay["host"]:
            raise DeliveryError("No sending service is configured. Open the Sending page.", ATTENTION)
        timeout, name = settings.SMTP_CLIENT_TIMEOUT_SECONDS, self._hostname()
        context = ssl.create_default_context()
        if relay["security"] == "ssl":
            connection: smtplib.SMTP = smtplib.SMTP_SSL(
                relay["host"], relay["port"], local_hostname=name, timeout=timeout, context=context)
        else:
            connection = smtplib.SMTP(relay["host"], relay["port"], local_hostname=name, timeout=timeout)
            connection.ehlo()
            if relay["security"] == "starttls":
                connection.starttls(context=context)
                connection.ehlo()
        if relay["username"]:
            connection.login(relay["username"], relay["password"])
        return connection

    def _send_via_relay(self, relay: dict, sender: str, recipient: str, data: bytes) -> None:
        connection = self._connect_relay(relay)
        try:
            connection.sendmail(sender, [recipient], data, mail_options=_body_options(connection, data))
        finally:
            _close(connection)

    def _send_direct(self, sender: str, recipient: str, data: bytes) -> None:
        domain = domain_of(recipient)
        try:
            hosts = [mx.host for mx in dns.resolve_mx(domain)] or [domain]  # no MX: the domain itself
        except dns.DnsError as error:
            raise DeliveryError(f"DNS lookup failed: {error}") from error
        last_error: Exception = DeliveryError("No mail server found.")
        for host in hosts[:_MAX_DIRECT_HOSTS]:
            try:
                connection = smtplib.SMTP(host, _DIRECT_PORT, local_hostname=self._hostname(),
                                          timeout=settings.SMTP_CLIENT_TIMEOUT_SECONDS)
                connection.ehlo()
                if connection.has_extn("starttls"):
                    # Server-to-server encryption is opportunistic: any certificate is accepted.
                    connection.starttls(context=ssl._create_unverified_context())  # noqa: S323
                    connection.ehlo()
                try:
                    connection.sendmail(sender, [recipient], data, mail_options=_body_options(connection, data))
                finally:
                    _close(connection)
                return
            except (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError, smtplib.SMTPSenderRefused) as error:
                raise error  # the server answered; another MX would give the same answer
            except Exception as error:  # noqa: BLE001 - try the next mail server
                last_error = error
        raise last_error


def _body_options(connection: smtplib.SMTP, data: bytes) -> list:
    """Messages with 8-bit text are announced as such when the server understands it."""
    return ["BODY=8BITMIME"] if connection.has_extn("8bitmime") and any(byte > 127 for byte in data) else []


def _close(connection: smtplib.SMTP) -> None:
    try:
        connection.quit()
    except (smtplib.SMTPException, OSError):
        connection.close()
