import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

from telethon import types
from telethon.errors import FloodWaitError

from src.integration.telegram_integration import (
    TelegramIntegration,
    TelegramListenerState,
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


class TelegramSubscriptionReadinessTests(unittest.IsolatedAsyncioTestCase):
    def make_integration(self, **kwargs):
        client = Mock()
        client.is_connected.return_value = True
        client.start = AsyncMock()
        client.get_input_entity = AsyncMock()
        client.run_until_disconnected = AsyncMock()
        client.disconnect = AsyncMock()
        with (
            patch(
                "src.integration.telegram_integration.StringSession",
                return_value=Mock(),
            ),
            patch(
                "src.integration.telegram_integration.TelegramClient",
                return_value=client,
            ),
        ):
            integration = TelegramIntegration(
                api_id=123,
                api_hash="api-hash",
                session_string="session",
                **kwargs,
            )
        return integration, client

    async def test_numeric_channel_activates_without_entity_resolution(self):
        integration, client = self.make_integration()
        integration.subscribe_to_new_messages(
            "-1002562064658",
            AsyncMock(),
        )

        await integration._activate_subscriptions()

        client.get_input_entity.assert_not_awaited()
        client.add_event_handler.assert_called_once()

    async def test_username_resolves_once_before_handler_activation(self):
        integration, client = self.make_integration()
        resolved = types.InputPeerChannel(
            channel_id=2562064658,
            access_hash=123,
        )
        client.get_input_entity.return_value = resolved
        integration.subscribe_to_new_messages("@upbit_news", AsyncMock())

        await integration._activate_subscriptions()
        await integration._activate_subscriptions()

        client.get_input_entity.assert_awaited_once_with("@upbit_news")
        client.add_event_handler.assert_called_once()
        self.assertEqual(
            integration.state,
            TelegramListenerState.RESOLVING_CHANNEL,
        )

    async def test_flood_wait_is_honored_without_disconnect_churn(self):
        integration, client = self.make_integration()
        resolved = types.InputPeerChannel(
            channel_id=2562064658,
            access_hash=123,
        )
        client.get_input_entity.side_effect = [
            FloodWaitError(request=None, capture=7),
            resolved,
        ]
        integration.subscribe_to_new_messages("@upbit_news", AsyncMock())

        async def finish_after_ready():
            integration._stop_event.set()

        client.run_until_disconnected.side_effect = finish_after_ready
        integration._wait_before_reconnect = AsyncMock()

        with patch(
            "src.integration.telegram_integration.record_health"
        ):
            await integration.run_forever()

        integration._wait_before_reconnect.assert_awaited_once_with(7.0)
        self.assertEqual(client.get_input_entity.await_count, 2)
        client.disconnect.assert_awaited_once()
        self.assertEqual(
            integration.state,
            TelegramListenerState.DISCONNECTED,
        )

    async def test_unexpected_internal_cancellation_recovers(self):
        integration, client = self.make_integration()
        integration.subscribe_to_new_messages(
            "-1002562064658",
            AsyncMock(),
        )
        attempts = 0

        async def start():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise asyncio.CancelledError()

        async def finish_after_ready():
            integration._stop_event.set()

        integration.start = AsyncMock(side_effect=start)
        integration._wait_before_reconnect = AsyncMock()
        client.run_until_disconnected.side_effect = finish_after_ready

        with (
            patch("src.integration.telegram_integration.record_health"),
            self.assertLogs(
                "src.integration.telegram_integration",
                level="ERROR",
            ) as logs,
        ):
            await integration.run_forever()

        self.assertEqual(integration.start.await_count, 2)
        self.assertTrue(
            any(
                "cancelled an in-flight operation unexpectedly" in line
                for line in logs.output
            )
        )

    def test_health_allows_only_bounded_recoverable_wait(self):
        integration, _ = self.make_integration(
            readiness_max_wait_seconds=30,
        )
        integration._set_state(
            TelegramListenerState.WAITING_FOR_FLOOD_LIMIT
        )

        self.assertTrue(
            integration._health_is_eligible(
                True,
                now=integration._state_changed_at + 30,
            )
        )
        self.assertFalse(
            integration._health_is_eligible(
                True,
                now=integration._state_changed_at + 31,
            )
        )
        self.assertFalse(integration._health_is_eligible(False))


if __name__ == "__main__":
    unittest.main()
