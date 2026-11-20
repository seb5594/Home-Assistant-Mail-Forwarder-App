import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support
from mailforwarder import ddns, network
from mailforwarder.ddns import CloudflareClient, DdnsError, DynamicDns
from mailforwarder.events import ActivityLog
from mailforwarder.state import State
from mailforwarder.store import ConfigStore


class FakeCloudflare:
    """Records calls like the Cloudflare API: zones by name, A records by host."""

    def __init__(self, records=None, zones=("example.test",)):
        self.records = records or []
        self.zones = zones
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.startswith("/zones?"):
            name = path.split("name=")[1]
            return [{"id": "zone1"}] if name in self.zones else []
        if method == "GET":
            return self.records
        return {"id": "new"}


class CloudflareTests(unittest.TestCase):
    def client(self, fake: FakeCloudflare) -> CloudflareClient:
        client = CloudflareClient("token")
        client._call = fake
        return client

    def test_zone_is_found_from_the_parent_domain(self):
        fake = FakeCloudflare()
        self.assertEqual(self.client(fake).zone_id("mail.example.test"), "zone1")

    def test_missing_zone_is_explained(self):
        with self.assertRaisesRegex(DdnsError, "No Cloudflare zone"):
            self.client(FakeCloudflare(zones=())).zone_id("mail.example.test")

    def test_missing_record_is_created_unproxied(self):
        fake = FakeCloudflare()
        self.assertEqual(self.client(fake).point_to("mail.example.test", "203.0.113.7"), "created")
        method, path, body = fake.calls[-1]
        self.assertEqual((method, path), ("POST", "/zones/zone1/dns_records"))
        self.assertEqual((body["content"], body["proxied"]), ("203.0.113.7", False))

    def test_changed_ip_updates_the_record_and_removes_the_proxy(self):
        fake = FakeCloudflare([{"id": "rec1", "content": "192.0.2.1", "proxied": True}])
        self.assertEqual(self.client(fake).point_to("mail.example.test", "203.0.113.7"), "updated")
        self.assertEqual(fake.calls[-1][:2], ("PATCH", "/zones/zone1/dns_records/rec1"))

    def test_current_record_is_left_alone(self):
        fake = FakeCloudflare([{"id": "rec1", "content": "203.0.113.7", "proxied": False}])
        self.assertEqual(self.client(fake).point_to("mail.example.test", "203.0.113.7"), "unchanged")
        self.assertEqual({c[0] for c in fake.calls}, {"GET"})


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = ConfigStore(Path(folder.name) / "forwarder.json")
        config = support.sample_config(587)
        config["domains"].append({"name": "family.duckdns.org", "kind": "duckdns"})
        config["dynamic_dns"] = {"duckdns": {"enabled": True, "token": "duck-token"},
                                 "cloudflare": {"enabled": True, "api_token": "cf-token"}}
        self.store.replace(config)
        self.state = State(Path(folder.name) / "state.json")
        self.updater = DynamicDns(self.store, self.state, ActivityLog())
        patch = mock.patch.object(network, "detect_public_ip", lambda force=False: "203.0.113.7")
        patch.start()
        self.addCleanup(patch.stop)

    def test_both_providers_are_updated_and_the_ip_is_remembered(self):
        fake = FakeCloudflare()
        with mock.patch.object(ddns, "update_duckdns") as duck, \
                mock.patch.object(CloudflareClient, "_call", lambda self, *a, **k: fake(*a, **k)):
            self.updater.update(force=True)
        duck.assert_called_once_with("duck-token", ["family.duckdns.org"], "203.0.113.7")
        status = self.updater.status()
        self.assertTrue(status["duckdns"]["ok"])
        self.assertTrue(status["cloudflare:mail.example.test"]["ok"])
        self.assertEqual(self.state.get("ddns_ip"), "203.0.113.7")

    def test_unchanged_ip_does_not_call_the_providers_again(self):
        fake = FakeCloudflare()
        with mock.patch.object(ddns, "update_duckdns") as duck, \
                mock.patch.object(CloudflareClient, "_call", lambda self, *a, **k: fake(*a, **k)):
            self.updater.update(force=True)
            self.updater.update()
        self.assertEqual(duck.call_count, 1)

    def test_a_failing_provider_is_reported_and_retried(self):
        with mock.patch.object(ddns, "update_duckdns", side_effect=DdnsError("KO")), \
                mock.patch.object(CloudflareClient, "_call", lambda self, *a, **k: FakeCloudflare()(*a, **k)):
            self.updater.update(force=True)
        self.assertFalse(self.updater.status()["duckdns"]["ok"])
        self.assertIsNone(self.state.get("ddns_ip"))

    def test_duckdns_answer_is_checked(self):
        class Answer:
            def __init__(self, text):
                self.text = text

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _size):
                return self.text.encode()

        with mock.patch("urllib.request.urlopen", return_value=Answer("OK")) as opened:
            ddns.update_duckdns("t", ["family.duckdns.org"], "203.0.113.7")
        self.assertIn("domains=family&token=t&ip=203.0.113.7", opened.call_args[0][0])
        with mock.patch("urllib.request.urlopen", return_value=Answer("KO")):
            with self.assertRaises(DdnsError):
                ddns.update_duckdns("t", ["family.duckdns.org"], "203.0.113.7")


if __name__ == "__main__":
    unittest.main()
