import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.integration.telegram_session import generate_session


class TelegramSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_exports_fresh_session_and_disconnects(self):
        client = MagicMock()
        client.start = AsyncMock()
        client.disconnect = AsyncMock()
        client.session.save.return_value = "new-session"
        with patch("src.integration.telegram_session.TelegramClient", return_value=client) as factory:
            result = await generate_session(123, "hash", "+35612345678")
        self.assertEqual(result, "new-session")
        self.assertIsNone(factory.call_args.args[0].auth_key)
        self.assertEqual(client.start.call_args.kwargs["phone"], "+35612345678")
        client.disconnect.assert_awaited_once()
        client.log_out.assert_not_called()

    async def test_disconnects_when_login_fails(self):
        client = MagicMock()
        client.start = AsyncMock(side_effect=RuntimeError("login failed"))
        client.disconnect = AsyncMock()
        with patch("src.integration.telegram_session.TelegramClient", return_value=client):
            with self.assertRaises(RuntimeError):
                await generate_session(123, "hash", "+35612345678")
        client.disconnect.assert_awaited_once()
        client.session.save.assert_not_called()

    async def test_invalid_configuration_does_not_connect(self):
        with patch("src.integration.telegram_session.TelegramClient") as factory:
            for api_id, api_hash, phone in [(0, "hash", "+123"), (123, "", "+123"), (123, "hash", "bot:token")]:
                with self.assertRaises(ValueError):
                    await generate_session(api_id, api_hash, phone)
            factory.assert_not_called()
