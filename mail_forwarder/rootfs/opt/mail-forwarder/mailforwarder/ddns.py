"""Keeps DNS records pointed at your home connection when its IP address changes.

Home internet connections get a new public IP now and then. Whoever sends you mail looks up your
mail host in DNS, so the record has to follow the IP. Two providers are supported:

* DuckDNS: the free ``something.duckdns.org`` domains,
* Cloudflare: the ``A`` record of the mail host of your own domains (DNS only, never proxied).
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from . import network, settings
from .events import ActivityLog
from .messages import Message
from .state import State
from .store import DUCKDNS_SUFFIX, ConfigStore, mail_host_of

_CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
_DUCKDNS_API = "https://www.duckdns.org/update"
_RECORD_TTL_SECONDS = 120


class DdnsError(Message):
    """An update failed; the code tells the web interface what the owner should check."""

    texts = {
        "no_ip": "Your public IP address could not be determined.",
        "duckdns_refused": "DuckDNS refused the update. Check the token and that the domain belongs to that account.",
        "duckdns_unreachable": "DuckDNS could not be reached: {detail}",
        "cf_error": "Cloudflare said: {detail}",
        "cf_unreachable": "Cloudflare could not be reached: {detail}",
        "cf_no_zone": "No Cloudflare zone for {host} was found with this token.",
    }


# ---- DuckDNS ---------------------------------------------------------------------------------

def update_duckdns(token: str, names: list, ip: str) -> None:
    subdomains = ",".join(name[: -len(DUCKDNS_SUFFIX)] for name in names)
    query = urllib.parse.urlencode({"domains": subdomains, "token": token, "ip": ip})
    try:
        with urllib.request.urlopen(f"{_DUCKDNS_API}?{query}", timeout=15) as response:  # noqa: S310
            answer = response.read(64).decode("ascii", "ignore").strip()
    except OSError as error:
        raise DdnsError("duckdns_unreachable", detail=str(error)) from error
    if not answer.startswith("OK"):
        raise DdnsError("duckdns_refused")


# ---- Cloudflare ------------------------------------------------------------------------------

class CloudflareClient:
    def __init__(self, token: str):
        self._token = token

    def _call(self, method: str, path: str, body: Optional[dict] = None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(f"{_CLOUDFLARE_API}{path}", data=data, method=method, headers={
            "Authorization": f"Bearer {self._token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
                reply = json.loads(response.read(2_000_000))
        except urllib.error.HTTPError as error:
            try:
                reply = json.loads(error.read(100_000))
            except ValueError:
                reply = {}
            problem = (reply.get("errors") or [{}])[0].get("message") or f"HTTP {error.code}"
            raise DdnsError("cf_error", detail=problem, denied=error.code in (401, 403)) from error
        except (OSError, ValueError) as error:
            raise DdnsError("cf_unreachable", detail=str(error)) from error
        if not reply.get("success"):
            raise DdnsError("cf_error", detail=(reply.get("errors") or [{}])[0].get("message") or "unknown error",
                            denied=False)
        return reply.get("result")

    def zone_id(self, hostname: str) -> str:
        """The zone that contains the host: tries ``a.b.c.com``, ``b.c.com``, ``c.com``."""
        labels = hostname.split(".")
        for start in range(len(labels) - 1):
            candidate = ".".join(labels[start:])
            zones = self._call("GET", "/zones?" + urllib.parse.urlencode({"name": candidate}))
            if zones:
                return zones[0]["id"]
        raise DdnsError("cf_no_zone", host=hostname)

    def point_to(self, hostname: str, ip: str) -> str:
        """Creates or updates the A record; returns what was done."""
        zone = self.zone_id(hostname)
        query = urllib.parse.urlencode({"type": "A", "name": hostname})
        records = self._call("GET", f"/zones/{zone}/dns_records?{query}")
        desired = {"type": "A", "name": hostname, "content": ip, "ttl": _RECORD_TTL_SECONDS, "proxied": False}
        if not records:
            self._call("POST", f"/zones/{zone}/dns_records", desired)
            return "created"
        record = records[0]
        if record.get("content") == ip and not record.get("proxied"):
            return "unchanged"
        self._call("PATCH", f"/zones/{zone}/dns_records/{record['id']}", desired)
        return "updated"


# ---- the updater -----------------------------------------------------------------------------

class DynamicDns:
    def __init__(self, store: ConfigStore, state: State, events: ActivityLog):
        self._store = store
        self._state = state
        self._events = events
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._results: dict = state.get("ddns_results", {})
        self._thread = threading.Thread(target=self._loop, name="dynamic-dns", daemon=True)
        self._last_generation = -1

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake.set()

    def run_soon(self) -> None:
        self._last_generation = -1  # forces an update even when the IP has not changed
        self._wake.set()

    def status(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._results))

    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                self.update(force=self._store.generation != self._last_generation)
            except Exception as error:  # noqa: BLE001 - the loop must never die
                self._events.warning(f"Dynamic DNS update failed unexpectedly: {error}", "ddns_crashed",
                                     detail=str(error))
            self._wake.wait(settings.DDNS_INTERVAL_SECONDS)
            self._wake.clear()

    def update(self, force: bool = False) -> None:
        config = self._store.get()
        duck, cloud = config["dynamic_dns"]["duckdns"], config["dynamic_dns"]["cloudflare"]
        if not (duck["enabled"] and duck["token"]) and not (cloud["enabled"] and cloud["api_token"]):
            return
        ip = network.detect_public_ip(force=True)
        if ip is None:
            self._record("all", False, "no_ip", {})
            return
        if ip == self._state.get("ddns_ip") and not force and self._all_ok():
            return
        self._last_generation = self._store.generation
        with self._lock:
            self._results = {}  # forget entries of domains that were removed meanwhile
        domains = config["domains"]
        if duck["enabled"] and duck["token"]:
            names = [d["name"] for d in domains if d["kind"] == "duckdns"]
            self._run("duckdns", names, lambda: (update_duckdns(duck["token"], names, ip), "updated")[1], ip)
        if cloud["enabled"] and cloud["api_token"]:
            client = CloudflareClient(cloud["api_token"])
            for domain in (d for d in domains if d["kind"] == "own"):
                host = mail_host_of(domain)
                self._run(f"cloudflare:{host}", [host], lambda host=host: client.point_to(host, ip), ip)
        if self._all_ok():
            self._state.set("ddns_ip", ip)

    def _run(self, key: str, hosts: list, action, ip: str) -> None:
        if not hosts:
            return
        try:
            outcome = action()
        except DdnsError as error:
            self._record(key, False, error.code, error.params)
            self._events.warning(f"Dynamic DNS ({key}): {error}", "ddns_failed", key=key,
                                 error_code=error.code, error_params=error.params)
            return
        self._record(key, True, "done", {"hosts": ", ".join(hosts), "ip": ip, "outcome": outcome})
        if outcome != "unchanged":
            self._events.info(f"Dynamic DNS: {', '.join(hosts)} now points to {ip}.", "ddns_updated",
                              hosts=", ".join(hosts), ip=ip)

    def _record(self, key: str, ok: bool, code: str, params: dict) -> None:
        with self._lock:
            self._results[key] = {"ok": ok, "code": code, "params": params, "time": time.time()}
            self._state.set("ddns_results", self._results)

    def _all_ok(self) -> bool:
        with self._lock:
            return bool(self._results) and all(entry["ok"] for entry in self._results.values())
