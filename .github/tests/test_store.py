import unittest

import support  # noqa: F401 - puts the app code on the import path
from mailforwarder import store
from mailforwarder.addresses import extract_path, is_valid_hostname, normalize_address
from mailforwarder.store import ConfigError


def valid_config() -> dict:
    return {
        "domains": [{"name": "Example.Test", "kind": "own", "mail_host": ""},
                    {"name": "family.duckdns.org", "kind": "duckdns"}],
        "people": [{"name": "Anna", "target": "Anna@Gmail.com", "addresses": [
            {"local": "info", "domain": "example.test"}, {"local": "anna", "domain": "family.duckdns.org"}]}],
    }


class AddressTests(unittest.TestCase):
    def test_addresses_are_normalised(self):
        self.assertEqual(normalize_address(" Max.Mustermann@Example.COM "), "max.mustermann@example.com")

    def test_invalid_addresses_are_rejected(self):
        for bad in ("", "no-at-sign", "a@b", "a b@example.com", "..x@example.com", "x@-bad.com"):
            self.assertIsNone(normalize_address(bad), bad)

    def test_hostnames_need_two_labels(self):
        self.assertTrue(is_valid_hostname("mail.example.com"))
        self.assertFalse(is_valid_hostname("localhost"))

    def test_smtp_paths_are_unwrapped(self):
        self.assertEqual(extract_path("<Bob@Example.com>"), "bob@example.com")
        self.assertEqual(extract_path("<>"), "")
        self.assertEqual(extract_path("<@relay.example:bob@example.com>"), "bob@example.com")


class NormalizeTests(unittest.TestCase):
    def test_defaults_are_filled_in(self):
        cleaned = store.normalize(valid_config())
        self.assertEqual(cleaned["domains"][0]["mail_host"], "mail.example.test")
        self.assertEqual(cleaned["domains"][1]["mail_host"], "family.duckdns.org")
        self.assertEqual(cleaned["people"][0]["target"], "anna@gmail.com")
        self.assertTrue(cleaned["people"][0]["id"])
        self.assertEqual(cleaned["delivery"]["mode"], "relay")

    def test_duckdns_domains_must_end_in_duckdns(self):
        config = valid_config()
        config["domains"][1]["name"] = "family.example.org"
        with self.assertRaises(ConfigError):
            store.normalize(config)

    def test_target_on_own_domain_is_refused_to_prevent_loops(self):
        config = valid_config()
        config["people"][0]["target"] = "anna@example.test"
        with self.assertRaisesRegex(ConfigError, "circles"):
            store.normalize(config)

    def test_address_cannot_belong_to_two_people(self):
        config = valid_config()
        config["people"].append({"name": "Ben", "target": "ben@web.de",
                                 "addresses": [{"local": "info", "domain": "example.test"}]})
        with self.assertRaisesRegex(ConfigError, "info@example.test"):
            store.normalize(config)

    def test_unknown_domain_in_address_is_refused(self):
        config = valid_config()
        config["people"][0]["addresses"][0]["domain"] = "other.test"
        with self.assertRaises(ConfigError):
            store.normalize(config)


class SecretTests(unittest.TestCase):
    def test_secrets_never_leave_the_store_and_empty_means_unchanged(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            config_store = store.ConfigStore(Path(folder) / "forwarder.json")
            first = valid_config()
            first["delivery"] = {"relay": {"host": "smtp.test", "username": "u", "password": "hunter2"}}
            masked = config_store.replace(first)
            self.assertEqual(masked["delivery"]["relay"]["password"], "")
            self.assertTrue(masked["delivery"]["relay"]["password_set"])
            second = valid_config()
            second["delivery"] = {"relay": {"host": "smtp.test", "username": "u", "password": ""}}
            config_store.replace(second)
            self.assertEqual(config_store.get()["delivery"]["relay"]["password"], "hunter2")

    def test_a_stored_secret_can_be_removed_explicitly(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            config_store = store.ConfigStore(Path(folder) / "forwarder.json")
            config = valid_config()
            config["dynamic_dns"] = {"cloudflare": {"enabled": True, "api_token": "cf-secret"}}
            config_store.replace(config)
            removal = valid_config()
            removal["dynamic_dns"] = {"cloudflare": {"enabled": False, "api_token": "", "api_token_clear": True}}
            masked = config_store.replace(removal)
            self.assertEqual(config_store.get()["dynamic_dns"]["cloudflare"]["api_token"], "")
            self.assertFalse(masked["dynamic_dns"]["cloudflare"]["api_token_set"])

    def test_errors_carry_a_code_and_parameters_for_translation(self):
        config = valid_config()
        config["people"][0]["target"] = "nonsense"
        with self.assertRaises(ConfigError) as caught:
            store.normalize(config)
        self.assertEqual((caught.exception.code, caught.exception.params["target"]), ("target_invalid", "nonsense"))

    def test_routes_cover_enabled_people_only(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            config_store = store.ConfigStore(Path(folder) / "forwarder.json")
            config = valid_config()
            config["people"].append({"name": "Off", "target": "off@web.de", "enabled": False,
                                     "addresses": [{"local": "off", "domain": "example.test"}]})
            config_store.replace(config)
            routes = config_store.routes()
            self.assertEqual(sorted(routes), ["anna@family.duckdns.org", "info@example.test"])
            self.assertEqual(routes["info@example.test"].target, "anna@gmail.com")


if __name__ == "__main__":
    unittest.main()
