import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from src.control.event.telegram_controller import TelegramController
from src.interface.trade_interface import run_workflows


class SharedTelegramLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.transport = Mock()
        self.transport.stop = AsyncMock()
        self.transport.run_forever = AsyncMock()
        self.transport.subscribe_to_new_messages.side_effect = ["upbit", "bithumb"]
        self.trader = AsyncMock()
        self.controllers = [TelegramController(
            telegram_kwargs={}, telegram=self.transport, channel=channel,
            message_handler=AsyncMock(),
        ) for channel in ("upbit", "bithumb")]
        self.workflows = [SimpleNamespace(event_control=controller, trade_control=self.trader)
                          for controller in self.controllers]

    async def test_stopping_one_channel_keeps_shared_transport_and_peer_active(self):
        for controller in self.controllers:
            await controller.start()
        await self.controllers[0].stop()
        self.transport.stop.assert_not_awaited()
        self.assertTrue(self.controllers[1]._accepting_messages)
        await self.controllers[1].stop()
        self.assertEqual(self.transport.unsubscribe.call_count, 2)

    async def test_cancellation_stops_connection_once_and_drains_both_workers(self):
        running = asyncio.Event()

        async def receive():
            self.assertEqual(self.transport.subscribe_to_new_messages.call_count, 2)
            running.set()
            await asyncio.Event().wait()

        self.transport.run_forever.side_effect = receive
        task = asyncio.create_task(run_workflows(self.workflows))
        try:
            await asyncio.wait_for(running.wait(), 1)
        finally:
            task.cancel()
            with self.assertLogs("src.interface.trade_interface", level="ERROR"):
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.transport.stop.assert_awaited_once()
        self.transport.run_forever.assert_awaited_once()
        self.trader.stop.assert_awaited_once()
        self.assertTrue(all(controller._worker_task is None for controller in self.controllers))

    async def test_partial_subscription_failure_cleans_up_without_connecting(self):
        self.transport.subscribe_to_new_messages.side_effect = ["upbit", ValueError("invalid channel")]
        with self.assertLogs("src.interface.trade_interface", level="ERROR"):
            with self.assertRaisesRegex(ValueError, "invalid channel"):
                await run_workflows(self.workflows)
        self.transport.run_forever.assert_not_awaited()
        self.transport.stop.assert_awaited_once()
        self.transport.unsubscribe.assert_called_once_with("upbit")
        self.trader.stop.assert_awaited_once()
        self.assertTrue(all(controller._worker_task is None for controller in self.controllers))
