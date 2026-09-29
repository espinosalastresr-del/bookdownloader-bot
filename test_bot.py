import os
import unittest

os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("LINK_SECRET", "test-link-secret")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("RENDER_EXTERNAL_URL", "https://example.onrender.com")

import bot


class RangeBridgeTests(unittest.TestCase):
    def test_signed_link_round_trip(self):
        token = bot.sign_link("file-id", "test.bin", 12345)
        payload = bot.verify_link(token)
        self.assertEqual(payload["file_id"], "file-id")
        self.assertEqual(payload["name"], "test.bin")
        self.assertEqual(payload["size"], 12345)

    def test_tampered_link_rejected(self):
        token = bot.sign_link("file-id", "test.bin", 12345)
        body, sig = token.split(".", 1)
        with self.assertRaises(Exception):
            bot.verify_link(body + "x." + sig)

    def test_range_parser(self):
        self.assertEqual(bot.parse_range("bytes=10-19", 100), (10, 19))
        self.assertEqual(bot.parse_range("bytes=10-", 100), (10, 99))

    def test_invalid_range(self):
        with self.assertRaises(Exception):
            bot.parse_range("bytes=100-101", 100)


if __name__ == "__main__":
    unittest.main()
