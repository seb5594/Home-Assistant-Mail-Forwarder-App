import json
import unittest
import urllib.error
import urllib.request

import support  # noqa: F401 - puts the app code on the import path
from support import FakeRelay, Harness, sample_config


class WebTests(unittest.TestCase):
    def setUp(self):
        self.relay = FakeRelay()
        self.addCleanup(self.relay.close)
        self.harness = Harness(sample_config(self.relay.port))
        self.addCleanup(self.harness.close)

    def get(self, path: str):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.harness.web_port}{path}", timeout=10) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def test_state_contains_everything_the_page_needs_and_no_secrets(self):
        status, body = self.harness.api("GET", "/api/state")
        self.assertEqual(status, 200)
        for key in ("version", "config", "queue", "stats", "checks", "presets", "ddns", "smtp_port"):
            self.assertIn(key, body)
        self.assertEqual(body["config"]["delivery"]["relay"]["password"], "")
        self.assertTrue(body["config"]["delivery"]["relay"]["password_set"])
        self.assertNotIn("secret", json.dumps(body["config"]))

    def test_config_can_be_saved_and_is_validated(self):
        _, state = self.harness.api("GET", "/api/state")
        config = state["config"]
        config["people"][0]["name"] = "Anna Schmidt"
        status, saved = self.harness.api("PUT", "/api/config", config)
        self.assertEqual(status, 200)
        self.assertEqual(saved["people"][0]["name"], "Anna Schmidt")
        self.assertEqual(self.harness.app.store.get()["delivery"]["relay"]["password"], "secret")

    def test_invalid_config_gets_a_readable_error(self):
        _, state = self.harness.api("GET", "/api/state")
        state["config"]["people"][0]["target"] = "not-an-address"
        status, body = self.harness.api("PUT", "/api/config", state["config"])
        self.assertEqual((status, body["code"]), (400, "target_invalid"))
        self.assertEqual(body["params"]["target"], "not-an-address")

    def test_posts_need_json(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.harness.web_port}/api/test-mail", data=b"x=1",
                                         method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=10)
        self.assertEqual(caught.exception.code, 415)

    def test_relay_login_can_be_tested(self):
        status, body = self.harness.api("POST", "/api/relay/test")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"], body)
        self.assertEqual(body["code"], "login_ok")

    def test_static_files_are_served_and_traversal_is_blocked(self):
        status, body, headers = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Mail Forwarder", body)
        self.assertEqual(self.get("/../../etc/passwd")[0], 404)
        self.assertEqual(self.get("/%2e%2e/%2e%2e/etc/passwd")[0], 404)

    def test_unknown_api_path_is_a_404(self):
        self.assertEqual(self.harness.api("GET", "/api/nothing")[0], 404)

    def test_other_clients_than_the_ingress_gateway_are_refused(self):
        from mailforwarder import settings
        original = settings.WEB_OPEN_TO_ALL, settings.ALLOWED_WEB_CLIENTS
        settings.ALLOWED_WEB_CLIENTS = frozenset({"172.30.32.2"})
        try:
            self.assertEqual(self.get("/api/state")[0], 403)
        finally:
            settings.WEB_OPEN_TO_ALL, settings.ALLOWED_WEB_CLIENTS = original


if __name__ == "__main__":
    unittest.main()
