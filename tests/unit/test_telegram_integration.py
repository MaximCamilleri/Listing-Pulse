import unittest
from unittest.mock import Mock, patch

from src.integration.telegram_integration import (
    TelegramIntegration,
    _normalize_channel_reference,
)


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


class TelegramIntegrationSessionTests(unittest.TestCase):
    @patch("src.integration.telegram_integration.TelegramClient")
    @patch("src.integration.telegram_integration.StringSession")
    def test_serialized_session_is_wrapped_as_string_session(
        self,
        string_session_class,
        telegram_client_class,
    ):
        string_session = Mock()
        string_session_class.return_value = string_session

        TelegramIntegration(
            api_id=123,
            api_hash="api-hash",
            session_string=" serialized-session ",
        )

        string_session_class.assert_called_once_with("serialized-session")
        self.assertIs(
            telegram_client_class.call_args.kwargs["session"],
            string_session,
        )

    def test_blank_serialized_session_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "session_string cannot be empty"):
            TelegramIntegration(
                api_id=123,
                api_hash="api-hash",
                session_string="   ",
            )


if __name__ == "__main__":
    unittest.main()
