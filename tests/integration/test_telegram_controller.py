import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from src.control.telegram_controller import TelegramController
from src.integration.telegram_integration import TelegramMessage


class FakeTelegramIntegration:
    def __init__(self, **_kwargs):
        self.handler = None
        self.stopped = asyncio.Event()

    def subscribe_to_new_messages(self, channel, handler):
        self.channel = channel
        self.handler = handler
        return "subscription-1"

    def unsubscribe(self, subscription_id):
        self.subscription_id = subscription_id

    async def run_forever(self):
        message = TelegramMessage(
            channel_id=123,
            channel_title="Listings",
            message_id=456,
            sender_id=None,
            text="New listing",
            date=datetime.now(timezone.utc),
            has_media=False,
            grouped_id=None,
        )
        await self.handler(message)
        await self.stopped.wait()

    async def stop(self):
        self.stopped.set()


class TelegramControllerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @patch(
        "src.control.telegram_controller.TelegramIntegration",
        FakeTelegramIntegration,
    )
    async def test_received_message_is_processed_and_shutdown_drains_queue(self):
        processed = asyncio.Event()
        handler = AsyncMock(side_effect=lambda _message: processed.set())
        controller = TelegramController(
            telegram_kwargs={},
            channel="listings",
            message_handler=handler,
        )

        run_task = asyncio.create_task(controller.run())
        await asyncio.wait_for(processed.wait(), timeout=1)
        await controller.stop()
        await asyncio.wait_for(run_task, timeout=1)

        handler.assert_awaited_once()
        self.assertEqual(handler.await_args.args[0].text, "New listing")
        self.assertEqual(controller._telegram.channel, "listings")
        self.assertEqual(controller._telegram.subscription_id, "subscription-1")


if __name__ == "__main__":
    unittest.main()
