"""The configuration that the user edits in the web interface.

The web interface always sends the complete configuration. It is checked and cleaned here, so
nothing else in the application has to deal with missing keys or malformed values.
"""
import copy
import ipaddress
import threading
import uuid
from pathlib import Path
from typing import NamedTuple, Optional

from .addresses import is_valid_hostname, is_valid_local_part, normalize_address
from .jsonfile import read_json, write_json

DOMAIN_KINDS = ("own", "duckdns")
DELIVERY_MODES = ("relay", "direct")
SECURITY_MODES = ("starttls", "ssl", "none")
DUCKDNS_SUFFIX = ".duckdns.org"

# Values that are never sent back to the browser. An empty value in an update keeps the stored one.
SECRET_FIELDS = (
    ("delivery", "relay", "password"),
    ("dynamic_dns", "duckdns", "token"),
    ("dynamic_dns", "cloudflare", "api_token"),
)


class ConfigError(ValueError):
    """The submitted configuration is not valid; the message is meant for the user."""


class Route(NamedTuple):
    """Where mail for one address goes."""
    person_id: str
    person: str
    target: str


def default_config() -> dict:
    return {
        "domains": [],
        "people": [],
        "delivery": {
            "mode": "relay",
            "sender_address": "",
            "rewrite_from": True,
            "relay": {
                "preset": "brevo",
                "host": "smtp-relay.brevo.com",
                "port": 587,
                "security": "starttls",
                "username": "",
                "password": "",
            },
        },
        "dynamic_dns": {
            "duckdns": {"enabled": False, "token": ""},
            "cloudflare": {"enabled": False, "api_token": ""},
        },
    }


def mail_host_of(domain: dict) -> str:
    """The host name that receives the mail of a domain (the target of its MX record)."""
    return domain["name"] if domain["kind"] == "duckdns" else domain["mail_host"]


# ---- normalisation ---------------------------------------------------------------------------

def _text(value, limit: int = 200) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _flag(value, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _host_or_ip(value: str) -> bool:
    if is_valid_hostname(value):
        return True
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _normalize_domains(raw) -> list:
    domains, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        name = _text(item.get("name")).lower().rstrip(".")
        kind = item.get("kind")
        if kind not in DOMAIN_KINDS:
            raise ConfigError(f"Unknown domain type for {name or 'a domain'}.")
        if not is_valid_hostname(name):
            raise ConfigError(f"'{name}' is not a valid domain name.")
        if kind == "duckdns" and not name.endswith(DUCKDNS_SUFFIX):
            raise ConfigError(f"A DuckDNS domain has to end with {DUCKDNS_SUFFIX}.")
        if name in seen:
            raise ConfigError(f"The domain {name} is listed twice.")
        seen.add(name)
        mail_host = _text(item.get("mail_host")).lower().rstrip(".") or f"mail.{name}"
        if kind == "own" and not is_valid_hostname(mail_host):
            raise ConfigError(f"'{mail_host}' is not a valid mail server name.")
        domains.append({"name": name, "kind": kind, "mail_host": mail_host if kind == "own" else name})
    return domains


def _normalize_people(raw, domain_names: set) -> list:
    people, claimed = [], {}
    for item in raw if isinstance(raw, list) else []:
        name = _text(item.get("name"), 60)
        target = normalize_address(_text(item.get("target")))
        if not name:
            raise ConfigError("Every person needs a name.")
        if target is None:
            raise ConfigError(f"'{_text(item.get('target'))}' is not a valid e-mail address for {name}.")
        if target.rpartition("@")[2] in domain_names:
            raise ConfigError(f"{name}: the mailbox {target} is on one of your own domains, "
                              "which would make mail go in circles. Use the real inbox, e.g. Gmail.")
        addresses = []
        for entry in item.get("addresses") or []:
            local = _text(entry.get("local")).lower()
            domain = _text(entry.get("domain")).lower()
            if not is_valid_local_part(local):
                raise ConfigError(f"'{local}' cannot be used as the first part of an address ({name}).")
            if domain not in domain_names:
                raise ConfigError(f"The domain '{domain}' of {name} is not in your domain list.")
            address = f"{local}@{domain}"
            if address in claimed:
                raise ConfigError(f"{address} is used by {claimed[address]} and {name}.")
            claimed[address] = name
            addresses.append({"local": local, "domain": domain})
        people.append({
            "id": _text(item.get("id"), 32) or uuid.uuid4().hex[:8],
            "name": name,
            "target": target,
            "enabled": _flag(item.get("enabled"), True),
            "addresses": addresses,
        })
    return people


def _normalize_delivery(raw: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    relay = raw.get("relay") if isinstance(raw.get("relay"), dict) else {}
    mode = raw.get("mode", "relay")
    security = relay.get("security", "starttls")
    if mode not in DELIVERY_MODES:
        raise ConfigError("Unknown sending method.")
    if security not in SECURITY_MODES:
        raise ConfigError("Unknown connection security.")
    sender = _text(raw.get("sender_address")).lower()
    if sender and normalize_address(sender) is None:
        raise ConfigError(f"'{sender}' is not a valid sender address.")
    host = _text(relay.get("host")).lower()
    if host and not _host_or_ip(host):
        raise ConfigError(f"'{host}' is not a valid mail server name.")
    try:
        port = int(relay.get("port") or 587)
    except (TypeError, ValueError):
        raise ConfigError("The port has to be a number.") from None
    if not 1 <= port <= 65535:
        raise ConfigError("The port has to be between 1 and 65535.")
    return {
        "mode": mode,
        "sender_address": sender,
        "rewrite_from": _flag(raw.get("rewrite_from"), True),
        "relay": {
            "preset": _text(relay.get("preset"), 32),
            "host": host,
            "port": port,
            "security": security,
            "username": _text(relay.get("username")),
            "password": str(relay.get("password") or ""),
        },
    }


def _normalize_dynamic_dns(raw: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    duckdns = raw.get("duckdns") if isinstance(raw.get("duckdns"), dict) else {}
    cloudflare = raw.get("cloudflare") if isinstance(raw.get("cloudflare"), dict) else {}
    return {
        "duckdns": {"enabled": _flag(duckdns.get("enabled")), "token": _text(duckdns.get("token"))},
        "cloudflare": {"enabled": _flag(cloudflare.get("enabled")),
                       "api_token": _text(cloudflare.get("api_token"))},
    }


def normalize(raw: dict) -> dict:
    """Returns a clean configuration or raises ConfigError."""
    if not isinstance(raw, dict):
        raise ConfigError("The configuration has to be an object.")
    domains = _normalize_domains(raw.get("domains"))
    return {
        "domains": domains,
        "people": _normalize_people(raw.get("people"), {d["name"] for d in domains}),
        "delivery": _normalize_delivery(raw.get("delivery")),
        "dynamic_dns": _normalize_dynamic_dns(raw.get("dynamic_dns")),
    }


# ---- secrets ---------------------------------------------------------------------------------

def _dig(config: dict, path: tuple, create: bool = False):
    """(the dictionary that holds the secret, its key). ``create`` fills in missing levels."""
    for key in path[:-1]:
        config = config.setdefault(key, {}) if create else config[key]
    return config, path[-1]


def mask_secrets(config: dict) -> dict:
    """A copy without secrets; ``<name>_set`` tells the browser whether one is stored."""
    masked = copy.deepcopy(config)
    for path in SECRET_FIELDS:
        holder, key = _dig(masked, path)
        holder[f"{key}_set"] = bool(holder.get(key))
        holder[key] = ""
    return masked


def keep_stored_secrets(incoming: dict, stored: dict) -> dict:
    """An empty secret in an update means 'unchanged'."""
    merged = copy.deepcopy(incoming)
    for path in SECRET_FIELDS:
        holder, key = _dig(merged, path, create=True)
        if not holder.get(key):
            holder[key] = _dig(stored, path)[0][key]
    return merged


# ---- the store -------------------------------------------------------------------------------

class ConfigStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        stored = read_json(path, None)
        try:
            self._config = normalize(stored) if stored else default_config()
        except ConfigError:
            self._config = default_config()
        self.generation = 0  # raised on every change, so other parts can notice

    def get(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._config)

    def masked(self) -> dict:
        return mask_secrets(self.get())

    def replace(self, incoming: dict) -> dict:
        """Validates, stores and returns the masked configuration."""
        with self._lock:
            cleaned = normalize(keep_stored_secrets(incoming, self._config) if isinstance(incoming, dict)
                                else incoming)
            write_json(self._path, cleaned, private=True)
            self._config = cleaned
            self.generation += 1
            return mask_secrets(cleaned)

    # ---- derived views -----------------------------------------------------------------------

    def routes(self) -> dict:
        """address -> Route for every address of every enabled person."""
        with self._lock:
            table = {}
            for person in self._config["people"]:
                if not person["enabled"]:
                    continue
                for entry in person["addresses"]:
                    table[f"{entry['local']}@{entry['domain']}"] = Route(
                        person["id"], person["name"], person["target"])
            return table

    def domain_names(self) -> set:
        with self._lock:
            return {domain["name"] for domain in self._config["domains"]}

    def domains(self) -> list:
        with self._lock:
            return copy.deepcopy(self._config["domains"])

    def greeting_host(self) -> str:
        """The name the SMTP server introduces itself with."""
        with self._lock:
            domains = self._config["domains"]
            return mail_host_of(domains[0]) if domains else "mail-forwarder.local"

    def first_address(self) -> Optional[str]:
        with self._lock:
            for person in self._config["people"]:
                for entry in person["addresses"]:
                    return f"{entry['local']}@{entry['domain']}"
            return None
