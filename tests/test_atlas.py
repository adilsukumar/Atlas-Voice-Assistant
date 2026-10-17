import os
import unittest
from unittest.mock import patch

from atlas import Action, execute, has_wake_word, parse_command, send_email


class AtlasTests(unittest.TestCase):
    def test_wake_word_is_required(self):
        self.assertFalse(has_wake_word("open excel"))
        self.assertFalse(has_wake_word("atlases"))
        self.assertTrue(has_wake_word("HEY ATLAS"))

    def test_command_case_and_wake_prefix(self):
        self.assertEqual(parse_command("Hey Atlas, OPEN EXCEL"), Action("app", "excel"))

    def test_ordinary_words_do_not_trigger_time(self):
        self.assertEqual(parse_command("sometime tomorrow").kind, "unknown")

    def test_search_url_is_encoded(self):
        self.assertEqual(parse_command("search cats & dogs").value, "https://www.google.com/search?q=cats+%26+dogs")

    def test_wiki_and_sleep(self):
        self.assertEqual(parse_command("who is ada lovelace"), Action("wiki", "ada lovelace"))
        self.assertEqual(parse_command("sleep").kind, "sleep")

    def test_dry_run_never_launches_browser(self):
        with patch("atlas.webbrowser.open") as launch:
            self.assertIn("Would open", execute(parse_command("open youtube"), dry_run=True))
            launch.assert_not_called()

    def test_dry_run_never_launches_office(self):
        with patch("atlas.subprocess.Popen") as launch:
            execute(parse_command("open word"), dry_run=True)
            launch.assert_not_called()

    def test_email_has_no_default_credentials(self):
        with patch.dict(os.environ, {}, clear=True), patch("atlas.smtplib.SMTP") as smtp:
            with self.assertRaises(ValueError):
                send_email("recipient@example.com", "subject", "message")
            smtp.assert_not_called()

    def test_email_rejects_header_injection(self):
        env = {"ATLAS_EMAIL_ADDRESS": "sender@example.com", "ATLAS_EMAIL_PASSWORD": "test-only-placeholder"}
        with patch.dict(os.environ, env, clear=True), patch("atlas.smtplib.SMTP") as smtp:
            with self.assertRaises(ValueError):
                send_email("recipient@example.com", "subject\nBcc: other@example.com", "message")
            smtp.assert_not_called()

    def test_time_and_date_work_without_voice_packages(self):
        self.assertIn("time", execute(Action("time")))
        self.assertIn("Today", execute(Action("date")))


if __name__ == "__main__":
    unittest.main()
