"""The web interface ships in two languages; these tests keep them complete and in step."""
import json
import re
import unittest

import support

WEB = support.CODE_DIR / "web"
KEY_CALL = re.compile(r"""\b(?:t|rich|richList|pairs|has|tn)\(\s*'([\w.]+)'""")
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def load(code: str) -> dict:
    return json.loads((WEB / "i18n" / f"{code}.json").read_text(encoding="utf-8"))


def flatten(node, prefix: str = "") -> dict:
    if isinstance(node, dict):
        flat = {}
        for key, value in node.items():
            flat.update(flatten(value, f"{prefix}{key}."))
        return flat
    return {prefix[:-1]: node}


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.english, self.german = flatten(load("en")), flatten(load("de"))

    def test_both_languages_have_the_same_keys(self):
        self.assertEqual(sorted(set(self.english) - set(self.german)), [], "missing in German")
        self.assertEqual(sorted(set(self.german) - set(self.english)), [], "missing in English")

    def test_placeholders_match_between_languages(self):
        for key, text in self.english.items():
            self.assertEqual(sorted(PLACEHOLDER.findall(json.dumps(text))),
                             sorted(PLACEHOLDER.findall(json.dumps(self.german[key]))), key)

    def test_nothing_is_left_untranslated(self):
        # The footer credit is the author's signature and stays in English; ddns.done is a pattern.
        deliberate = {"footer.developed", "ddns.done"}
        same = [key for key, text in self.english.items() if key not in deliberate
                and isinstance(text, str) and text == self.german[key] and len(text) > 25]
        self.assertEqual(same, [])

    def test_every_key_used_in_the_page_exists(self):
        used = set()
        for script in (WEB / "js").rglob("*.js"):
            used.update(KEY_CALL.findall(script.read_text(encoding="utf-8")))
        known = set(self.english) | {key.rsplit(".", 1)[0] for key in self.english} | \
            {key.rsplit(".", 2)[0] for key in self.english}
        missing = sorted(key for key in used if key not in known and f"{key}_one" not in self.english)
        self.assertEqual(missing, [])

    def test_every_message_code_of_the_app_has_a_text(self):
        from mailforwarder.delivery import DeliveryError
        from mailforwarder.ddns import DdnsError
        from mailforwarder.store import ConfigError
        from mailforwarder.web import ApiError
        for namespace, error in (("delivery", DeliveryError), ("ddns", DdnsError),
                                 ("errors", ConfigError), ("errors", ApiError)):
            for code in error.texts:
                self.assertIn(f"{namespace}.{code}", self.english, f"{error.__name__}: {code}")

    def test_every_health_check_has_a_title(self):
        diagnostics = (support.CODE_DIR / "mailforwarder" / "diagnostics.py").read_text()
        kinds = set(re.findall(r'Check\([^,]+, "[a-z]+", "(\w+)"', diagnostics))
        kinds.update(re.findall(r'"(dns_a|dns_mx|dns_aaaa|dns_error|out_relay|out_port25|in_traffic)"', diagnostics))
        self.assertTrue(kinds)
        for kind in kinds:
            self.assertIn(f"checks.{kind}.title", self.english, kind)


if __name__ == "__main__":
    unittest.main()
