import unittest

from src.integration.telegram_integration import _normalize_channel_reference


class TelegramChannelReferenceTests(unittest.TestCase):
    def test_normalizes_numeric_string_as_channel_id(self):
        self.assertEqual(
            _normalize_channel_reference("-4350134025"),
            -1004350134025,
        )

    def test_preserves_marked_channel_id(self):
        self.assertEqual(
            _normalize_channel_reference(-1004350134025),
            -1004350134025,
        )

    def test_preserves_channel_username(self):
        self.assertEqual(
            _normalize_channel_reference("upbit_news"),
            "upbit_news",
        )

    def test_rejects_blank_channel(self):
        with self.assertRaises(ValueError):
            _normalize_channel_reference("  ")


if __name__ == "__main__":
    unittest.main()
