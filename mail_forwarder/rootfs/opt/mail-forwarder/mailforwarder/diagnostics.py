"""The health checks behind the traffic-light list on the overview page.

Each check answers one question a beginner would otherwise have to debug blindly, and every
check that fails says in plain words what is wrong and what to do about it.
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
    id: str
    group: str  # setup | app | internet | dns | outbound
    title: str
    status: str
    detail: str = ""
    fix: list = field(default_factory=list)
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
        ok, detail = self._deliverer.test_login()
        with self._lock:
            self._login = {"ok": ok, "detail": detail, "time": time.time()}
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
                items.append(Check("internal", "app", "A check could not run", WARN, str(error)))
        return items

    def _setup_checks(self, config: dict) -> list:
        delivery = config["delivery"]
        has_address = any(p["enabled"] and p["addresses"] for p in config["people"])
        relay = delivery["relay"]
        sending_ready = delivery["mode"] == "direct" or bool(
            relay["host"] and delivery["sender_address"] and (not relay["username"] or relay["password"]))
        return [
            Check("setup.domain", "setup", "A domain is added",
                  OK if config["domains"] else TODO,
                  "" if config["domains"] else "Mail needs an address to be sent to. Add your domain first.",
                  guide="domains"),
            Check("setup.mailbox", "setup", "A person with an address is added",
                  OK if has_address else TODO,
                  "" if has_address else "Say who gets the mail: a name, one or more addresses and the real inbox.",
                  guide="mailboxes"),
            Check("setup.sending", "setup", "Sending is set up",
                  OK if sending_ready else TODO,
                  "" if sending_ready else "Choose how forwarded mail leaves: through a sending service (recommended).",
                  guide="sending"),
        ]

    def _app_checks(self, _config: dict) -> list:
        reachable, detail = network.probe_tcp("127.0.0.1", settings.SMTP_PORT, timeout=3)
        checks = [Check(
            "app.listener", "app", "The mail receiver is running",
            OK if reachable else ERROR,
            f"Listening on port {settings.SMTP_PORT}." if reachable else detail,
            [] if reachable else ["Open the app's log tab and look for errors.", "Restart the app."])]
        known, host_port = supervisor.published_port(settings.SMTP_PORT)
        if not known:
            checks.append(Check("app.port", "app", "Port 25 is published by Home Assistant", UNKNOWN,
                                "The Supervisor could not be asked about the port mapping."))
        elif host_port is None:
            checks.append(Check(
                "app.port", "app", "Port 25 is published by Home Assistant", ERROR,
                f"Container port {settings.SMTP_PORT} is not published, so nothing outside can reach the receiver.",
                ["Open this app in Home Assistant, go to 'Configuration' and then 'Network'.",
                 f"Enter {settings.SMTP_PORT} next to '{settings.SMTP_PORT}/tcp' and save.",
                 "Restart the app."], guide="network"))
        else:
            checks.append(Check("app.port", "app", "Port 25 is published by Home Assistant", OK,
                                f"Container port {settings.SMTP_PORT} is reachable on port {host_port} "
                                "of your Home Assistant computer."))
        return checks

    def _internet_checks(self, _config: dict) -> list:
        ip = network.detect_public_ip(force=True)
        if ip is None:
            return [Check("net.ip", "internet", "Your public IP address is known", WARN,
                          "No lookup service answered. Is outbound HTTPS blocked?",
                          ["Check that this Home Assistant can open websites.",
                           "Checks that depend on your public IP are skipped until this works."])]
        return [Check("net.ip", "internet", "Your public IP address is known", OK, ip)]

    def _dns_checks(self, config: dict) -> list:
        ip = network.detect_public_ip()
        checks: list = []
        for domain in config["domains"]:
            try:
                checks += self._dns_checks_for(domain, ip)
            except dns.DnsError as error:
                checks.append(Check(f"dns.{domain['name']}", "dns", f"DNS of {domain['name']}", UNKNOWN,
                                    f"DNS over HTTPS is not reachable: {error}",
                                    ["Allow outbound HTTPS to cloudflare-dns.com or dns.google."]))
        return checks

    @staticmethod
    def _dns_checks_for(domain: dict, ip: Optional[str]) -> list:
        name, host = domain["name"], mail_host_of(domain)
        checks: list = []
        addresses = dns.resolve(host, "A")
        title = f"{host} points to your home"
        if not addresses:
            fix = ["Create an A record for it, or switch on dynamic DNS on the Domains page."]
            checks.append(Check(f"dns.a.{name}", "dns", title, ERROR, f"{host} has no A record yet.", fix, "domains"))
        elif any(network.is_cloudflare_proxy(a) for a in addresses):
            checks.append(Check(f"dns.a.{name}", "dns", title, ERROR,
                                f"{host} is proxied by Cloudflare (orange cloud). A proxy does not forward mail.",
                                [f"In Cloudflare, open the DNS records of {name}.",
                                 f"Click the orange cloud next to {host} so that it turns grey ('DNS only')."],
                                "domains"))
        elif ip is None:
            checks.append(Check(f"dns.a.{name}", "dns", title, UNKNOWN,
                                f"{host} points to {', '.join(addresses)}; your own IP is unknown."))
        elif ip in addresses:
            checks.append(Check(f"dns.a.{name}", "dns", title, OK, f"{host} -> {ip}"))
        else:
            checks.append(Check(f"dns.a.{name}", "dns", title, ERROR,
                                f"{host} points to {', '.join(addresses)}, but your public IP is {ip}.",
                                ["Change the A record to your current IP, or switch on dynamic DNS on the "
                                 "Domains page so that it follows your IP automatically.",
                                 "Wait a few minutes after changing it and run the checks again."], "domains"))
        if domain["kind"] == "own":
            checks.append(Diagnostics._mx_check(name, host))
        if dns.resolve(host, "AAAA"):
            checks.append(Check(f"dns.aaaa.{name}", "dns", f"{host} has no IPv6 address", WARN,
                                "Senders prefer IPv6 when it exists, and this app is not set up for it.",
                                ["Delete the AAAA record of this host, or forward port 25 for IPv6 as well."],
                                "network"))
        return checks

    @staticmethod
    def _mx_check(name: str, host: str) -> Check:
        title = f"{name} tells senders where to deliver (MX)"
        exchangers = dns.resolve_mx(name)
        if not exchangers:
            return Check(f"dns.mx.{name}", "dns", title, ERROR, f"{name} has no MX record.",
                         [f"Add an MX record for {name} with the mail server {host} and priority 10."], "domains")
        if exchangers[0].host != host:
            others = ", ".join(f"{mx.host} (priority {mx.priority})" for mx in exchangers)
            return Check(f"dns.mx.{name}", "dns", title, ERROR,
                         f"The preferred mail server of {name} is {exchangers[0].host}, not {host}. Found: {others}.",
                         [f"Remove other MX records of {name}, for example from Cloudflare Email Routing, "
                          f"and keep only {host}."], "domains")
        if len(exchangers) > 1:
            return Check(f"dns.mx.{name}", "dns", title, WARN,
                         "More than one MX record exists. Senders fall back to the others when yours is busy.",
                         ["Remove the extra MX records unless you want them as a backup."], "domains")
        return Check(f"dns.mx.{name}", "dns", title, OK, f"{name} -> {host}")

    def _outbound_checks(self, config: dict) -> list:
        delivery = config["delivery"]
        if delivery["mode"] == "relay":
            relay = delivery["relay"]
            if not relay["host"]:
                return [Check("out.relay", "outbound", "The sending service can be reached", TODO,
                              "No sending service is chosen yet.", guide="sending")]
            ok, detail = network.probe_tcp(relay["host"], relay["port"])
            return [Check("out.relay", "outbound",
                          f"The sending service can be reached ({relay['host']}:{relay['port']})",
                          OK if ok else ERROR, detail if ok else detail,
                          [] if ok else [
                              f"Your network blocks outbound connections to port {relay['port']}.",
                              "Allow it in your firewall, or try port 2525 or 465 if your service offers them."],
                          "" if ok else "sending")]
        ok, detail = network.probe_tcp(GMAIL_MX, 25)
        return [Check("out.port25", "outbound", "Outbound port 25 is open", OK if ok else ERROR, detail,
                      [] if ok else ["Most internet providers and many firewalls block outgoing port 25.",
                                     "Switch to a sending service on the Sending page: it uses port 587."],
                      "" if ok else "sending")]

    def _evidence_checks(self, _config: dict) -> list:
        seen = self._stats.snapshot()["last_outside_connection"]
        if seen:
            return [Check("in.traffic", "internet", "A mail server from the internet has connected", OK,
                          f"Last connection from {seen['address']}.")]
        return [Check(
            "in.traffic", "internet", "A mail server from the internet has connected", PENDING,
            "No outside connection to this app has been seen yet. That is normal until your router forwards "
            "port 25 and someone (or the test button) sends mail.",
            ["Forward port 25 in your router, see the Network page.", "Then press 'Send test mail' on the overview."],
            "network")]


def _verdict(items: list) -> str:
    """One word for the banner: setup, problem, unverified or ready."""
    if any(item.id.startswith("setup.") and item.status == TODO for item in items):
        return "setup"
    if any(item.status == ERROR for item in items):
        return "problem"
    if any(item.id == "in.traffic" and item.status == PENDING for item in items):
        return "unverified"
    return "ready" if items else "unknown"
