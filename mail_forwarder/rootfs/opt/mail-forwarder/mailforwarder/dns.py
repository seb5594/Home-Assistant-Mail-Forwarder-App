"""DNS lookups over HTTPS (JSON API).

Asking a public resolver over port 443 has two advantages for this application: it works
behind routers that hijack or block port 53 (common with OPNsense and Pi-hole setups), and it
shows what the *internet* sees for your domain, not what your local DNS server answers.
"""
import json
import threading
import time
import urllib.parse
import urllib.request
from typing import NamedTuple

from . import settings

RESOLVERS = (
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
)
RECORD_TYPES = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "TXT": 16, "AAAA": 28}
_TIMEOUT_SECONDS = 6


class DnsError(Exception):
    """No resolver could be reached."""


class MailExchanger(NamedTuple):
    priority: int
    host: str


_cache: dict = {}
_cache_lock = threading.Lock()


def _fetch(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read(1_000_000))


def resolve(name: str, record_type: str) -> list:
    """The answers (as text) of one record type; an empty list means the record does not exist."""
    key = (name.lower(), record_type)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and time.time() - cached[0] < settings.DNS_CACHE_SECONDS:
            return list(cached[1])

    wanted = RECORD_TYPES[record_type]
    last_error = "no resolver answered"
    for resolver in RESOLVERS:
        query = urllib.parse.urlencode({"name": name, "type": record_type})
        try:
            reply = _fetch(f"{resolver}?{query}")
        except (OSError, ValueError) as error:
            last_error = str(error)
            continue
        # Status 0 = fine, 3 = the name does not exist. Anything else is a resolver problem.
        if reply.get("Status") not in (0, 3):
            last_error = f"resolver status {reply.get('Status')}"
            continue
        answers = [item["data"] for item in reply.get("Answer", []) if item.get("type") == wanted]
        with _cache_lock:
            _cache[key] = (time.time(), answers)
        return list(answers)
    raise DnsError(last_error)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def resolve_mx(name: str) -> list:
    """MX records of a name, best (lowest priority number) first."""
    exchangers = []
    for answer in resolve(name, "MX"):
        priority, _, host = answer.partition(" ")
        if priority.isdigit() and host:
            exchangers.append(MailExchanger(int(priority), host.rstrip(".").lower()))
    return sorted(exchangers)


def resolve_txt(name: str) -> list:
    """TXT records with the quotes removed and split strings joined."""
    return [answer.replace('" "', "").strip('"') for answer in resolve(name, "TXT")]
