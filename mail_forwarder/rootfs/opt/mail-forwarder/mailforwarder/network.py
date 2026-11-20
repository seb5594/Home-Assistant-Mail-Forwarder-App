"""Small network helpers: public IP, reachability of ports, and recognising Cloudflare's proxy."""
import ipaddress
import socket
import threading
import time
import urllib.request
from typing import Optional

from . import settings

IP_SOURCES = (
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://checkip.amazonaws.com",
)

# Addresses that Cloudflare's orange-cloud proxy answers with (https://www.cloudflare.com/ips-v4).
# A mail host that resolves into these ranges is proxied, and a proxy never forwards mail.
CLOUDFLARE_RANGES = tuple(ipaddress.ip_network(net) for net in (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
))

_ip_cache: dict = {"value": None, "at": 0.0}
_ip_lock = threading.Lock()


def is_cloudflare_proxy(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in CLOUDFLARE_RANGES if network.version == ip.version)


def is_public_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def detect_public_ip(force: bool = False) -> Optional[str]:
    """The IPv4 address the internet sees, or None if no lookup service answered."""
    with _ip_lock:
        if not force and _ip_cache["value"] and time.time() - _ip_cache["at"] < settings.PUBLIC_IP_CACHE_SECONDS:
            return _ip_cache["value"]
    for source in IP_SOURCES:
        try:
            with urllib.request.urlopen(source, timeout=6) as response:  # noqa: S310
                text = response.read(64).decode("ascii", "ignore").strip()
            if is_public_address(text) and ipaddress.ip_address(text).version == 4:
                with _ip_lock:
                    _ip_cache.update(value=text, at=time.time())
                return text
        except (OSError, ValueError):
            continue
    return None


def cached_public_ip() -> Optional[str]:
    """The last IP that was found, without any network traffic (for the status page)."""
    with _ip_lock:
        return _ip_cache["value"]


def probe_tcp(host: str, port: int, timeout: float = 8.0) -> tuple:
    """(reachable, detail). Also reads the greeting of mail servers, which proves that the
    connection is not just accepted by a firewall that answers on behalf of the destination."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            if port in (25, 587, 2525):
                greeting = connection.recv(256).decode("ascii", "replace").strip()
                if not greeting.startswith("220"):
                    return False, f"Connected, but the server did not greet like a mail server: {greeting[:80]!r}"
                return True, greeting.splitlines()[0][:100]
            return True, "connected"
    except socket.gaierror:
        return False, f"The name {host} could not be resolved."
    except socket.timeout:
        return False, "Timed out. A firewall is probably silently dropping the traffic."
    except ConnectionRefusedError:
        return False, "Connection refused: nothing is listening there, or a firewall rejects it."
    except OSError as error:
        return False, str(error)
