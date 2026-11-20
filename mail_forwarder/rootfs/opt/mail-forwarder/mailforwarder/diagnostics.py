"""The health checks behind the traffic-light list on the overview page.

Each check answers one question a beginner would otherwise have to debug blindly. A check does
not carry prose: it names what it looked at (``kind``), what it found (``code``) and the values
involved (``params``). The web interface turns that into a title, an explanation and the steps
to fix it in the language of the browser (``checks.<kind>.title`` and ``checks.<kind>.<code>.*``).
"""
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from . import dns, network, settings, supervisor
from .delivery import Deliverer
from .stats import Stats
from .store import ConfigStore, mail_host_of
from .testmail import TestTracker

OK, WARN, ERROR, TODO, PENDING, UNKNOWN = "ok", "warn", "error", "todo", "pending", "unknown"
GMAIL_MX = "gmail-smtp-in.l.google.com"


@dataclass
class Check:
    id: str  # unique, e.g. dns.a.example.com
    group: str  # setup | app | internet | dns | outbound
    kind: str  # what was examined: the key of the title
    status: str
    code: str = ""  # what was found: the key of the explanation and the fix steps
    params: dict = field(default_factory=dict)
    guide: str = ""  # the page of the web interface that explains the fix


class Diagnostics:
    def __init__(self, store: ConfigStore, stats: Stats, tests: TestTracker, deliverer: Deliverer):
        self._store = store
        self._stats = stats
        self._tests = tests
        self._deliverer = deliverer
        self._lock = threading.Lock()
        self._items: list = []
        self._updated: Optional[float] = None
        self._running = False
        self._login: Optional[dict] = None

    # ---- running -----------------------------------------------------------------------------

    def run_in_background(self) -> bool:
        """Starts a run unless one is already going. Returns False in that case."""
        with self._lock:
            if self._running:
                return False
            self._running = True
        threading.Thread(target=self._run, name="diagnostics", daemon=True).start()
        return True

    def run_now(self) -> None:
        with self._lock:
            self._running = True
        self._run()

    def _run(self) -> None:
        try:
            items = self._collect()
        finally:
            with self._lock:
                self._running = False
        with self._lock:
            self._items, self._updated = items, time.time()

    def check_login(self) -> dict:
        """The explicit 'test login' button: this really connects to the sending service."""
        ok, code, params = self._deliverer.test_login()
        with self._lock:
            self._login = {"ok": ok, "code": code, "params": params, "time": time.time()}
            return dict(self._login)

    def snapshot(self) -> dict:
        with self._lock:
            items = [asdict(item) for item in self._items]
            login = dict(self._login) if self._login else None
            return {"running": self._running, "updated": self._updated, "items": items,
                    "login": login, "verdict": _verdict(self._items)}

    # ---- collecting --------------------------------------------------------------------------

    def _collect(self) -> list:
        config = self._store.get()
        items: list = []
        for part in (self._setup_checks, self._app_checks, self._internet_checks,
                     self._dns_checks, self._outbound_checks, self._evidence_checks):
            try:
                items += part(config)
            except Exception as error:  # noqa: BLE001 - one broken group must not hide the others
                items.append(Check("internal", "app", "internal", WARN, "failed", {"detail": str(error)}))
        return items

    def _setup_checks(self, config: dict) -> list:
        delivery, relay = config["delivery"], config["delivery"]["relay"]
        has_address = any(p["enabled"] and p["addresses"] for p in config["people"])
        sending_ready = delivery["mode"] == "direct" or bool(
            relay["host"] and delivery["sender_address"] and (not relay["username"] or relay["password"]))
        return [
            Check("setup.domain", "setup", "setup_domain", OK if config["domains"] else TODO,
                  "ok" if config["domains"] else "todo", guide="domains"),
            Check("setup.mailbox", "setup", "setup_mailbox", OK if has_address else TODO,
                  "ok" if has_address else "todo", guide="mailboxes"),
            Check("setup.sending", "setup", "setup_sending", OK if sending_ready else TODO,
                  "ok" if sending_ready else "todo", guide="sending"),
        ]

    def _app_checks(self, _config: dict) -> list:
        port = settings.SMTP_PORT
        reachable, _, _ = network.probe_tcp("127.0.0.1", port, timeout=3)
        checks = [Check("app.listener", "app", "app_listener", OK if reachable else ERROR,
                        "ok" if reachable else "down", {"port": port})]
        known, host_port = supervisor.published_port(port)
        if not known:
            checks.append(Check("app.port", "app", "app_port", UNKNOWN, "unknown", {"port": port}))
        elif host_port is None:
            checks.append(Check("app.port", "app", "app_port", ERROR, "unpublished", {"port": port}, "network"))
        else:
            checks.append(Check("app.port", "app", "app_port", OK, "ok", {"port": port, "host_port": host_port}))
        return checks

    def _internet_checks(self, _config: dict) -> list:
        ip = network.detect_public_ip(force=True)
        if ip is None:
            return [Check("net.ip", "internet", "net_ip", WARN, "unknown")]
        return [Check("net.ip", "internet", "net_ip", OK, "ok", {"ip": ip})]

    def _dns_checks(self, config: dict) -> list:
        ip = network.detect_public_ip()
        checks: list = []
        for domain in config["domains"]:
            try:
                checks += self._dns_checks_for(domain, ip)
            except dns.DnsError as error:
                checks.append(Check(f"dns.error.{domain['name']}", "dns", "dns_error", UNKNOWN, "unreachable",
                                    {"domain": domain["name"], "detail": str(error)}))
        return checks

    @staticmethod
    def _dns_checks_for(domain: dict, ip: Optional[str]) -> list:
        name, host = domain["name"], mail_host_of(domain)
        base = {"domain": name, "host": host}
        checks: list = []
        addresses = dns.resolve(host, "A")
        found = {**base, "addresses": ", ".join(addresses), "ip": ip or ""}
        if not addresses:
            status, code = ERROR, "none"
        elif any(network.is_cloudflare_proxy(a) for a in addresses):
            status, code = ERROR, "proxied"
        elif ip is None:
            status, code = UNKNOWN, "unknown_ip"
        elif ip in addresses:
            status, code = OK, "ok"
        else:
            status, code = ERROR, "mismatch"
        checks.append(Check(f"dns.a.{name}", "dns", "dns_a", status, code, found, "" if status == OK else "domains"))
        if domain["kind"] == "own":
            checks.append(Diagnostics._mx_check(name, host))
        if dns.resolve(host, "AAAA"):
            checks.append(Check(f"dns.aaaa.{name}", "dns", "dns_aaaa", WARN, "present", base, "network"))
        return checks

    @staticmethod
    def _mx_check(name: str, host: str) -> Check:
        base = {"domain": name, "host": host}
        exchangers = dns.resolve_mx(name)
        if not exchangers:
            return Check(f"dns.mx.{name}", "dns", "dns_mx", ERROR, "missing", base, "domains")
        if exchangers[0].host != host:
            found = ", ".join(f"{mx.host} ({mx.priority})" for mx in exchangers)
            return Check(f"dns.mx.{name}", "dns", "dns_mx", ERROR, "wrong",
                         {**base, "first": exchangers[0].host, "found": found}, "domains")
        if len(exchangers) > 1:
            return Check(f"dns.mx.{name}", "dns", "dns_mx", WARN, "many", base, "domains")
        return Check(f"dns.mx.{name}", "dns", "dns_mx", OK, "ok", base)

    def _outbound_checks(self, config: dict) -> list:
        delivery = config["delivery"]
        if delivery["mode"] == "relay":
            relay = delivery["relay"]
            params = {"host": relay["host"], "port": relay["port"]}
            if not relay["host"]:
                return [Check("out.relay", "outbound", "out_relay", TODO, "todo", params, "sending")]
            ok, probe, detail = network.probe_tcp(relay["host"], relay["port"])
            return [Check("out.relay", "outbound", "out_relay", OK if ok else ERROR, "ok" if ok else "blocked",
                          {**params, "probe": probe, "detail": detail}, "" if ok else "sending")]
        ok, probe, detail = network.probe_tcp(GMAIL_MX, 25)
        return [Check("out.port25", "outbound", "out_port25", OK if ok else ERROR, "ok" if ok else "blocked",
                      {"probe": probe, "detail": detail}, "" if ok else "sending")]

    def _evidence_checks(self, _config: dict) -> list:
        seen = self._stats.snapshot()["last_outside_connection"]
        if seen:
            return [Check("in.traffic", "internet", "in_traffic", OK, "ok", {"address": seen["address"]})]
        return [Check("in.traffic", "internet", "in_traffic", PENDING, "none", {}, "network")]


def _verdict(items: list) -> str:
    """One word for the banner: setup, problem, unverified or ready."""
    if any(item.id.startswith("setup.") and item.status == TODO for item in items):
        return "setup"
    if any(item.status == ERROR for item in items):
        return "problem"
    if any(item.id == "in.traffic" and item.status == PENDING for item in items):
        return "unverified"
    return "ready" if items else "unknown"
