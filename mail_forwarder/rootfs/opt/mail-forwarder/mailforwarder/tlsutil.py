"""A self-signed certificate so that other mail servers can encrypt their connection (STARTTLS).

Mail servers talk to each other with opportunistic encryption: they accept any certificate and
only want *some* encryption instead of none. A self-signed certificate is therefore enough here.
"""
import shutil
import ssl
import subprocess
from pathlib import Path
from typing import Optional

from .events import ActivityLog

_RENEW_BEFORE_SECONDS = 30 * 86400


class TlsProvider:
    """Hands out a server-side TLS context for the current host name, creating the key if needed."""

    def __init__(self, directory: Path, events: ActivityLog):
        self._directory = directory
        self._events = events
        self._context: Optional[ssl.SSLContext] = None
        self._hostname = ""
        self._failed_for = ""

    def context_for(self, hostname: str) -> Optional[ssl.SSLContext]:
        if hostname == self._hostname and self._context is not None:
            return self._context
        if hostname == self._failed_for:
            return None
        paths = self._ensure_certificate(hostname)
        if paths is None:
            self._failed_for = hostname
            return None
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(*paths)
        self._context, self._hostname = context, hostname
        return context

    def _ensure_certificate(self, hostname: str) -> Optional[tuple]:
        self._directory.mkdir(parents=True, exist_ok=True)
        certificate, key = self._directory / "server.crt", self._directory / "server.key"
        marker = self._directory / "hostname"
        current = marker.read_text().strip() if marker.exists() else ""
        if certificate.exists() and key.exists() and current == hostname and self._still_valid(certificate):
            return str(certificate), str(key)
        if shutil.which("openssl") is None:
            self._events.warning("openssl is missing, so mail will be received without encryption.")
            return None
        command = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes", "-days", "3650",
                   "-subj", f"/CN={hostname}", "-addext", f"subjectAltName=DNS:{hostname}",
                   "-keyout", str(key), "-out", str(certificate)]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=60)
        except (subprocess.SubprocessError, OSError) as error:
            self._events.warning(f"Could not create a TLS certificate, mail is received unencrypted: {error}")
            return None
        key.chmod(0o600)
        marker.write_text(hostname)
        self._events.info(f"Created a TLS certificate for {hostname}.")
        return str(certificate), str(key)

    @staticmethod
    def _still_valid(certificate: Path) -> bool:
        if shutil.which("openssl") is None:
            return True  # cannot check, and cannot renew either
        result = subprocess.run(["openssl", "x509", "-checkend", str(_RENEW_BEFORE_SECONDS), "-noout",
                                 "-in", str(certificate)], capture_output=True, check=False)
        return result.returncode == 0
