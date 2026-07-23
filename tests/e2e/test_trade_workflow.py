import asyncio
import threading
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.config.settings import settings
from src.integration.telegram_integration import TelegramMessage
from src.interface.trade_interface import start_trader


class WorkflowTelegramController:
    instance = None

    def __init__(self, *, telegram_kwargs, channel, message_handler):
        type(self).instance = self
        self.telegram_kwargs = telegram_kwargs
        self.channel = channel
        self.message_handler = message_handler
        self.stopped = asyncio.Event()

    async def run(self):
        await self.message_handler(
            TelegramMessage(
                channel_id=123,
                channel_title="Listings",
                message_id=456,
                sender_id=None,
                text="[거래] 비트코인 (BTC) 신규 거래지원 안내 (KRW, BTC, USDT)",
                date=datetime.now(timezone.utc),
                has_media=False,
                grouped_id=None,
            )
        )
        await self.stop()

    async def stop(self):
        self.stopped.set()


class TradeWorkflowEndToEndTests(unittest.IsolatedAsyncioTestCase):
    @patch("src.interface.trade_interface.TelegramController", WorkflowTelegramController)
    @patch("src.interface.trade_interface.BinanceController")
    async def test_telegram_message_triggers_configured_binance_trade(
        self,
        binance_controller_class,
    ):
        binance = binance_controller_class.return_value
        binance.place_market_order = AsyncMock(
            return_value=(
                SimpleNamespace(
                    update_time=int(datetime.now(timezone.utc).timestamp() * 1_000)
                ),
                SimpleNamespace(),
            )
        )
        stop_event = threading.Event()

        await asyncio.wait_for(start_trader(stop_event), timeout=1)

        binance.place_market_order.assert_awaited_once_with(
            symbol="BTCUSDT",
            quantity=settings.order_quantity,
            direction=settings.order_direction,
            callback_rate=settings.order_callback_rate,
        )
        self.assertEqual(
            WorkflowTelegramController.instance.channel,
            settings.telegram_channel,
        )
        self.assertEqual(
            WorkflowTelegramController.instance.telegram_kwargs["session_string"],
            settings.telegram_session,
        )
        self.assertTrue(stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
