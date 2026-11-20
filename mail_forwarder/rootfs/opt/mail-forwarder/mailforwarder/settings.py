"""Paths, ports and limits shared by every module.

Everything can be overridden through ``MF_*`` environment variables, which is how the tests
run the whole application inside a temporary directory on unprivileged ports.
"""
import os
from pathlib import Path


def _path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def _number(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


# ---- storage ---------------------------------------------------------------------------------
DATA_DIR = _path("MF_DATA_DIR", "/data")
CONFIG_FILE = DATA_DIR / "forwarder.json"
STATE_FILE = DATA_DIR / "state.json"
SPOOL_DIR = DATA_DIR / "spool"
FAILED_DIR = DATA_DIR / "failed"
TLS_DIR = DATA_DIR / "tls"

WEB_ROOT = _path("MF_WEB_ROOT", "/opt/mail-forwarder/web")
VERSION_FILE = _path("MF_VERSION_FILE", "/etc/mail-forwarder/version")
OPTIONS_FILE = _path("MF_OPTIONS_FILE", "/data/options.json")

# ---- network ---------------------------------------------------------------------------------
SMTP_BIND = os.environ.get("MF_SMTP_BIND", "0.0.0.0")
SMTP_PORT = _number("MF_SMTP_PORT", 25)
WEB_BIND = os.environ.get("MF_WEB_BIND", "0.0.0.0")
WEB_PORT = _number("MF_WEB_PORT", 8099)

# Only the Supervisor's ingress gateway (and the container itself) may open the web interface.
INGRESS_GATEWAY = "172.30.32.2"
ALLOWED_WEB_CLIENTS = frozenset({INGRESS_GATEWAY, "127.0.0.1", "::1"})
WEB_OPEN_TO_ALL = os.environ.get("MF_WEB_OPEN") == "1"

SUPERVISOR_URL = os.environ.get("MF_SUPERVISOR_URL", "http://supervisor")

# ---- SMTP receiver limits --------------------------------------------------------------------
MAX_MESSAGE_BYTES = 25 * 1024 * 1024  # what the big mail providers accept as well
MAX_RECIPIENTS = 20
MAX_CONNECTIONS = 20
MAX_BAD_RECIPIENTS = 6  # a session that guesses this many unknown addresses is dropped
MAX_RECEIVED_HEADERS = 30  # more hops than this means the message is going in circles
IDLE_TIMEOUT_SECONDS = 120
MAX_LINE_BYTES = 1024 * 1024

# ---- delivery --------------------------------------------------------------------------------
MAX_QUEUE_ITEMS = 500
DELIVERY_THREADS = 2
SMTP_CLIENT_TIMEOUT_SECONDS = 45
# Minutes to wait after the 1st, 2nd, ... failed attempt; after the last one the message is parked.
RETRY_DELAYS_MINUTES = (1, 5, 15, 60, 180, 360, 720, 720, 720, 720)
ATTENTION_RETRY_MINUTES = 30  # errors that need the owner to fix a setting
FAILED_RETENTION_DAYS = 14
SPOOL_SCAN_SECONDS = 15

# ---- background jobs -------------------------------------------------------------------------
DDNS_INTERVAL_SECONDS = 300
PUBLIC_IP_CACHE_SECONDS = 60
DNS_CACHE_SECONDS = 20
TEST_MAIL_TIMEOUT_SECONDS = 240

# Marks the test message that the "send test mail" button creates.
TEST_HEADER = "X-Mail-Forwarder-Test"


def read_version() -> str:
    try:
        return VERSION_FILE.read_text().strip() or "dev"
    except OSError:
        return "dev"
