import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from mailforwarder import dns, network, supervisor
from mailforwarder.diagnostics import Diagnostics
from mailforwarder.state import State
from mailforwarder.stats import Stats
from mailforwarder.store import ConfigStore
from mailforwarder.testmail import TestTracker

PUBLIC_IP = "203.0.113.7"
CONFIG = support.sample_config(587)
CONFIG["domains"].append({"name": "family.duckdns.org", "kind": "duckdns"})


class Dns:
    """Answers DNS questions from a table: {(name, type): [answers]}."""

    def __init__(self, table: dict):
        self.table = table

    def __call__(self, name: str, record_type: str) -> list:
        return self.table.get((name, record_type), [])


GOOD_DNS = {
    ("mail.example.test", "A"): [PUBLIC_IP],
    ("example.test", "MX"): ["10 mail.example.test."],
    ("family.duckdns.org", "A"): [PUBLIC_IP],
}


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = ConfigStore(Path(folder.name) / "forwarder.json")
        self.store.replace(CONFIG)
        self.stats = Stats(State(Path(folder.name) / "state.json"))
        self.diagnostics = Diagnostics(self.store, self.stats, TestTracker(), mock.Mock())
        self.dns_table = dict(GOOD_DNS)
        self.published = (True, 25)
        self.reachable = (True, "greeting", "220 ready")
        patches = [
            mock.patch.object(dns, "resolve", lambda n, t: Dns(self.dns_table)(n, t)),
            mock.patch.object(network, "detect_public_ip", lambda force=False: PUBLIC_IP),
            mock.patch.object(network, "probe_tcp", lambda host, port, timeout=8: self.reachable),
            mock.patch.object(supervisor, "published_port", lambda port: self.published),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def run_checks(self) -> dict:
        self.diagnostics.run_now()
        return {item["id"]: item for item in self.diagnostics.snapshot()["items"]}

    def test_a_healthy_setup_waits_for_the_first_outside_connection(self):
        checks = self.run_checks()
        self.assertEqual([c["status"] for c in checks.values() if c["status"] == "error"], [])
        self.assertEqual(self.diagnostics.snapshot()["verdict"], "unverified")
        self.stats.connection("8.8.4.4")
        self.run_checks()
        self.assertEqual(self.diagnostics.snapshot()["verdict"], "ready")

    def test_an_empty_installation_asks_for_setup(self):
        self.store.replace({})
        self.run_checks()
        self.assertEqual(self.diagnostics.snapshot()["verdict"], "setup")

    def test_unpublished_port_is_reported_with_the_fix(self):
        self.published = (True, None)
        check = self.run_checks()["app.port"]
        self.assertEqual((check["status"], check["code"]), ("error", "unpublished"))
        self.assertEqual(check["guide"], "network")

    def test_cloudflare_proxy_is_recognised(self):
        self.dns_table[("mail.example.test", "A")] = ["104.21.5.5"]
        check = self.run_checks()["dns.a.example.test"]
        self.assertEqual((check["status"], check["code"]), ("error", "proxied"))

    def test_outdated_ip_in_dns_is_reported(self):
        self.dns_table[("mail.example.test", "A")] = ["192.0.2.1"]
        check = self.run_checks()["dns.a.example.test"]
        self.assertEqual((check["status"], check["code"]), ("error", "mismatch"))
        self.assertEqual(check["params"]["ip"], PUBLIC_IP)
        self.assertEqual(check["params"]["addresses"], "192.0.2.1")

    def test_foreign_mx_record_is_an_error(self):
        self.dns_table[("example.test", "MX")] = ["1 route1.mx.cloudflare.net."]
        check = self.run_checks()["dns.mx.example.test"]
        self.assertEqual((check["status"], check["code"]), ("error", "wrong"))
        self.assertIn("route1.mx.cloudflare.net", check["params"]["found"])

    def test_missing_mx_record_is_an_error(self):
        del self.dns_table[("example.test", "MX")]
        self.assertEqual(self.run_checks()["dns.mx.example.test"]["status"], "error")

    def test_duckdns_domain_needs_no_mx_record(self):
        checks = self.run_checks()
        self.assertNotIn("dns.mx.family.duckdns.org", checks)
        self.assertEqual(checks["dns.a.family.duckdns.org"]["status"], "ok")

    def test_ipv6_record_is_a_warning(self):
        self.dns_table[("mail.example.test", "AAAA")] = ["2001:db8::1"]
        self.assertEqual(self.run_checks()["dns.aaaa.example.test"]["status"], "warn")

    def test_blocked_sending_port_is_an_error(self):
        self.reachable = (False, "timeout", "")
        check = self.run_checks()["out.relay"]
        self.assertEqual((check["status"], check["code"]), ("error", "blocked"))
        self.assertEqual(check["params"]["probe"], "timeout")

    def test_unreachable_dns_is_unknown_not_an_error(self):
        def broken(name, record_type):
            raise dns.DnsError("offline")
        with mock.patch.object(dns, "resolve", broken):
            checks = self.run_checks()
        self.assertEqual(checks["dns.error.example.test"]["status"], "unknown")


class DnsClientTests(unittest.TestCase):
    def setUp(self):
        dns.clear_cache()
        self.addCleanup(dns.clear_cache)

    def test_answers_are_filtered_by_record_type(self):
        reply = {"Status": 0, "Answer": [{"type": 5, "data": "alias.example."}, {"type": 15, "data": "20 b.example."},
                                         {"type": 15, "data": "10 a.example."}]}
        with mock.patch.object(dns, "_fetch", return_value=reply):
            self.assertEqual([mx.host for mx in dns.resolve_mx("example.org")], ["a.example", "b.example"])

    def test_missing_name_is_an_empty_answer(self):
        with mock.patch.object(dns, "_fetch", return_value={"Status": 3}):
            self.assertEqual(dns.resolve("nope.example", "A"), [])

    def test_second_resolver_is_used_when_the_first_fails(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if "cloudflare" in url:
                raise OSError("down")
            return {"Status": 0, "Answer": [{"type": 1, "data": "192.0.2.5"}]}
        with mock.patch.object(dns, "_fetch", fetch):
            self.assertEqual(dns.resolve("example.org", "A"), ["192.0.2.5"])
        self.assertEqual(len(calls), 2)

    def test_all_resolvers_down_raises(self):
        with mock.patch.object(dns, "_fetch", side_effect=OSError("down")):
            with self.assertRaises(dns.DnsError):
                dns.resolve("example.org", "A")

    def test_txt_strings_are_joined(self):
        reply = {"Status": 0, "Answer": [{"type": 16, "data": '"v=spf1 " "-all"'}]}
        with mock.patch.object(dns, "_fetch", return_value=reply):
            self.assertEqual(dns.resolve_txt("example.org"), ["v=spf1 -all"])


class NetworkTests(unittest.TestCase):
    def test_cloudflare_ranges(self):
        self.assertTrue(network.is_cloudflare_proxy("104.21.5.5"))
        self.assertTrue(network.is_cloudflare_proxy("172.67.1.1"))
        self.assertFalse(network.is_cloudflare_proxy("203.0.113.7"))
        self.assertFalse(network.is_cloudflare_proxy("not an ip"))

    def test_public_addresses(self):
        self.assertTrue(network.is_public_address("8.8.8.8"))
        for private in ("192.168.1.5", "10.0.0.1", "100.64.1.1", "127.0.0.1"):
            self.assertFalse(network.is_public_address(private), private)


if __name__ == "__main__":
    unittest.main()
