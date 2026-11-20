"""The whole path: SMTP in -> queue -> sending service out, against a pretend sending service."""
import smtplib
import unittest

import support  # noqa: F401 - puts the app code on the import path
from mailforwarder import settings
from mailforwarder.rewrite import header_value
from support import FakeRelay, Harness, sample_config, wait_for

MAIL = (b"From: Bob Sender <bob@sender.example>\r\nTo: info@example.test\r\nSubject: Greetings\r\n"
        b"\r\nHello Anna!\r\n.leading dot line\r\n")


class PipelineCase(unittest.TestCase):
    def setUp(self):
        self.relay = FakeRelay()
        self.addCleanup(self.relay.close)
        self.harness = Harness(sample_config(self.relay.port))
        self.addCleanup(self.harness.close)
        self.app = self.harness.app


class ReceiverTests(PipelineCase):
    def test_unknown_user_is_refused_while_the_conversation_runs(self):
        with self.assertRaises(smtplib.SMTPRecipientsRefused) as caught:
            self.harness.send("bob@sender.example", ["nobody@example.test"], MAIL)
        self.assertEqual(caught.exception.recipients["nobody@example.test"][0], 550)
        self.assertEqual(self.app.spool.counts()["queued"], 0)

    def test_foreign_domain_is_not_relayed(self):
        with self.assertRaises(smtplib.SMTPRecipientsRefused) as caught:
            self.harness.send("bob@sender.example", ["someone@gmail.com"], MAIL)
        self.assertEqual(caught.exception.recipients["someone@gmail.com"][0], 550)
        self.assertIn(b"Relay access denied", caught.exception.recipients["someone@gmail.com"][1])

    def test_disabled_person_gets_no_mail(self):
        config = self.app.store.get()
        config["people"][0]["enabled"] = False
        self.app.store.replace(config)
        with self.assertRaises(smtplib.SMTPRecipientsRefused):
            self.harness.send("bob@sender.example", ["info@example.test"], MAIL)

    def test_a_session_that_guesses_addresses_is_dropped(self):
        with smtplib.SMTP("127.0.0.1", self.harness.smtp_port, local_hostname="scanner.example") as client:
            client.ehlo()
            client.mail("x@scanner.example")
            with self.assertRaises(smtplib.SMTPServerDisconnected):
                for number in range(settings.MAX_BAD_RECIPIENTS + 2):
                    client.rcpt(f"guess{number}@example.test")

    def test_too_large_messages_are_announced_as_such(self):
        with smtplib.SMTP("127.0.0.1", self.harness.smtp_port, local_hostname="sender.example") as client:
            client.ehlo()
            code, _ = client.mail("x@sender.example", options=[f"SIZE={settings.MAX_MESSAGE_BYTES + 1}"])
            self.assertEqual(code, 552)

    def test_starttls_is_offered_and_works(self):
        import shutil
        import ssl
        if shutil.which("openssl") is None:
            self.skipTest("openssl is not installed")
        with smtplib.SMTP("127.0.0.1", self.harness.smtp_port, local_hostname="sender.example") as client:
            client.ehlo()
            self.assertTrue(client.has_extn("starttls"))
            insecure = ssl.create_default_context()
            insecure.check_hostname, insecure.verify_mode = False, ssl.CERT_NONE
            self.assertEqual(client.starttls(context=insecure)[0], 220)
            client.sendmail("bob@sender.example", ["info@example.test"], MAIL)
        self.assertIn("ESMTPS", self.app.spool.read_raw(self.app.spool.queued()[0]).decode())

    def test_mail_loops_are_stopped(self):
        looping = b"Received: from x\r\n" * (settings.MAX_RECEIVED_HEADERS + 1) + MAIL
        with self.assertRaises(smtplib.SMTPDataError) as caught:
            self.harness.send("bob@sender.example", ["info@example.test"], looping)
        self.assertEqual(caught.exception.smtp_code, 554)


class ForwardingTests(PipelineCase):
    def test_message_is_forwarded_to_the_real_mailbox(self):
        self.harness.send("bob@sender.example", ["info@example.test"], MAIL)
        sent = wait_for(lambda: self.relay.messages)[0]
        self.assertEqual(sent["recipients"], ["anna@mailbox.test"])
        self.assertEqual(sent["sender"], "forward@example.test")
        self.assertEqual(header_value(sent["data"], "X-Original-To"), "info@example.test")
        self.assertIn("bob@sender.example", header_value(sent["data"], "Reply-To"))
        self.assertTrue(sent["data"].endswith(b"\r\n\r\nHello Anna!\r\n.leading dot line\r\n"))
        self.assertEqual(self.relay.logins, [("user", "secret")])
        wait_for(lambda: self.app.spool.counts() == {"queued": 0, "failed": 0})
        self.assertEqual(self.app.stats.snapshot()["forwarded"], 1)

    def test_every_inbox_of_a_person_gets_its_own_copy(self):
        config = self.app.store.get()
        config["people"][0]["targets"] = ["anna@mailbox.test", "ben@mailbox.test"]
        self.app.store.replace(config)
        self.harness.send("bob@sender.example", ["info@example.test"], MAIL)
        wait_for(lambda: len(self.relay.messages) == 2)
        self.assertEqual(sorted(m["recipients"][0] for m in self.relay.messages),
                         ["anna@mailbox.test", "ben@mailbox.test"])

    def test_one_message_for_two_addresses_of_the_same_person_is_sent_once(self):
        config = self.app.store.get()
        config["people"][0]["addresses"].append({"local": "anna", "domain": "example.test"})
        self.app.store.replace(config)
        self.harness.send("bob@sender.example", ["info@example.test", "anna@example.test"], MAIL)
        wait_for(lambda: self.relay.messages)
        self.assertEqual(len(self.relay.messages), 1)
        self.assertEqual(header_value(self.relay.messages[0]["data"], "X-Original-To"),
                         "anna@example.test, info@example.test")

    def test_wrong_login_keeps_the_message_and_asks_for_attention(self):
        config = self.app.store.get()
        config["delivery"]["relay"]["password"] = "wrong"
        self.app.store.replace(config)
        self.harness.send("bob@sender.example", ["info@example.test"], MAIL)
        job = wait_for(lambda: next((j for j in self.app.spool.queued() if j.attempts), None))
        self.assertTrue(job.needs_attention)
        self.assertEqual(job.error_code, "login_rejected")
        self.assertIn("535", job.error_params["detail"])
        self.assertGreater(job.next_attempt, 0)
        self.assertEqual(self.relay.messages, [])

    def test_message_goes_out_after_the_setting_is_fixed(self):
        config = self.app.store.get()
        config["delivery"]["relay"]["password"] = "wrong"
        self.app.store.replace(config)
        self.harness.send("bob@sender.example", ["info@example.test"], MAIL)
        job = wait_for(lambda: next((j for j in self.app.spool.queued() if j.attempts), None))
        config["delivery"]["relay"]["password"] = "secret"
        self.app.store.replace(config)
        self.assertTrue(self.app.spool.retry_now(job.id))
        self.app.worker.wake()
        wait_for(lambda: self.relay.messages)

    def test_refused_recipient_is_parked_and_can_be_retried(self):
        self.relay.refuse_recipients = ("anna@mailbox.test",)
        self.harness.send("bob@sender.example", ["info@example.test"], MAIL)
        failed = wait_for(lambda: self.app.spool.failed())[0]
        self.assertEqual(failed.error_code, "recipient_refused")
        self.assertEqual(self.app.spool.counts(), {"queued": 0, "failed": 1})
        self.relay.refuse_recipients = ()
        status, _ = self.harness.api("POST", f"/api/queue/{failed.id}/retry")
        self.assertEqual(status, 200)
        wait_for(lambda: self.relay.messages)

    def test_missing_sender_address_is_reported_as_a_setting_to_fix(self):
        config = self.app.store.get()
        config["delivery"]["sender_address"] = ""
        config["delivery"]["relay"]["username"] = ""
        self.app.store.replace(config)
        self.harness.send("bob@sender.example", ["info@example.test"], MAIL)
        job = wait_for(lambda: next((j for j in self.app.spool.queued() if j.attempts), None))
        self.assertEqual(job.error_code, "no_sender")


class TestMailTests(PipelineCase):
    def test_test_mail_travels_out_and_back_in(self):
        self.relay.loop_back_domains = ("example.test",)
        self.relay.loop_back_to = ("127.0.0.1", self.harness.smtp_port)
        status, body = self.harness.api("POST", "/api/test-mail", {"address": "info@example.test"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "running")
        wait_for(lambda: self.app.tests.snapshot()["status"] == "ok", timeout=15)
        steps = self.app.tests.snapshot()["steps"]
        self.assertTrue(steps["sent"] and steps["arrived"] and steps["forwarded"])
        # one message to the alias (out) and one forwarded copy to the mailbox
        self.assertEqual(sorted(r for m in self.relay.messages for r in m["recipients"]),
                         ["anna@mailbox.test", "info@example.test"])

    def test_test_mail_reports_a_sending_problem(self):
        config = self.app.store.get()
        config["delivery"]["relay"]["password"] = "wrong"
        self.app.store.replace(config)
        self.harness.api("POST", "/api/test-mail", {"address": "info@example.test"})
        wait_for(lambda: self.app.tests.snapshot()["status"] == "failed")
        self.assertEqual(self.app.tests.snapshot()["error"]["code"], "login_rejected")

    def test_test_mail_needs_one_of_your_addresses(self):
        status, body = self.harness.api("POST", "/api/test-mail", {"address": "stranger@elsewhere.test"})
        self.assertEqual((status, body["code"]), (400, "test_address"))


if __name__ == "__main__":
    unittest.main()
