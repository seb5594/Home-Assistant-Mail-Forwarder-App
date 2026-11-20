import unittest

import support  # noqa: F401
from mailforwarder.rewrite import ForwardPlan, build_forward_message, header_value, sender_label

RAW = (b"Received: from a by b\r\nReturn-Path: <bounce@example.org>\r\n"
       b"From: =?utf-8?q?J=C3=BCrgen_M=C3=BCller?= <jm@example.org>\r\nSubject: Hello\r\n there\r\n"
       b"To: info@example.test\r\n\r\nBody line 1\r\n.dot line\r\n")
PLAN = ForwardPlan("info@example.test", "forward@example.test", True)


class RewriteTests(unittest.TestCase):
    def forwarded(self, plan=PLAN, raw=RAW) -> bytes:
        return build_forward_message(raw, plan)

    def test_body_stays_byte_for_byte(self):
        self.assertTrue(self.forwarded().endswith(b"\r\n\r\nBody line 1\r\n.dot line\r\n"))

    def test_from_moves_to_display_name_and_reply_to(self):
        message = self.forwarded()
        self.assertIn("jm@example.org", header_value(message, "Reply-To"))
        sender = header_value(message, "From")
        self.assertIn("Jürgen Müller (jm@example.org)", sender)
        self.assertIn("<forward@example.test>", sender)
        self.assertIn("jm@example.org", header_value(message, "X-Original-From"))

    def test_existing_reply_to_is_kept(self):
        raw = RAW.replace(b"To: info", b"Reply-To: team@example.org\r\nTo: info")
        message = self.forwarded(raw=raw)
        self.assertEqual(header_value(message, "Reply-To"), "team@example.org")

    def test_rewrite_can_be_switched_off(self):
        message = self.forwarded(ForwardPlan("info@example.test", "forward@example.test", False))
        self.assertIn("jm@example.org", header_value(message, "From"))
        self.assertNotIn("Reply-To", message.decode("utf-8", "replace").split("\r\n\r\n")[0])

    def test_trace_headers_are_added_and_return_path_dropped(self):
        message = self.forwarded()
        self.assertEqual(header_value(message, "X-Original-To"), "info@example.test")
        self.assertIsNotNone(header_value(message, "X-Forwarded-By"))
        self.assertIsNone(header_value(message, "Return-Path"))

    def test_folded_headers_survive(self):
        self.assertEqual(header_value(self.forwarded(), "Subject"), "Hello there")

    def test_message_without_headers_does_not_crash(self):
        message = self.forwarded(raw=b"\r\njust a body\r\n")
        self.assertTrue(message.endswith(b"just a body\r\n"))

    def test_sender_label_variants(self):
        self.assertEqual(sender_label("", "a@b.org"), "a@b.org")
        self.assertEqual(sender_label("Anna", "a@b.org"), "Anna (a@b.org)")
        self.assertEqual(sender_label("Anna <a@b.org>", "a@b.org"), "Anna <a@b.org>")
        self.assertEqual(sender_label("", ""), "Unknown sender")


if __name__ == "__main__":
    unittest.main()
