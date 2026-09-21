import asyncio
import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from src.config.settings import settings
from src.integration.telegram_integration import TelegramMessage
from src.interface.trade_interface import start_trader


class MultiTradeWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_both_notice_sources_reach_shared_binance_controller(self):
        stop_event = threading.Event()
        processed = set()
        listeners = []
        notices = {
            "upbit": "[거래] 비트코인(BTC) 신규 거래지원 안내 (KRW, BTC, USDT)",
            "bithumb": "[마켓 추가] 이더리움(ETH) 원화 마켓 추가 안내",
        }

        class Listener:
            def __init__(self, *, telegram_kwargs, channel, message_handler, telegram=None):
                self.telegram = self
                self.channel = channel
                self.handler = message_handler
                self.stopped = asyncio.Event()
                listeners.append(self)

            async def start(self):
                pass

            async def run_forever(self):
                await self.handler(TelegramMessage(
                    channel_id=123, channel_title=self.channel, message_id=456,
                    sender_id=None, text=notices[self.channel],
                    date=datetime.now(timezone.utc), has_media=False, grouped_id=None,
                ))
                processed.add(self.channel)
                if len(processed) == 2:
                    stop_event.set()
                await self.stopped.wait()

            async def stop(self):
                self.stopped.set()

        with (
            patch("src.control.event.listener_factory.TelegramController", Listener),
            patch("src.control.event_to_trade.BinanceController") as factory,
            patch.object(settings, "upbit_telegram_channel", "upbit"),
            patch.object(settings, "bithumb_telegram_channel", "bithumb"),
        ):
            trader = factory.return_value
            trader.start = AsyncMock()
            trader.stop = AsyncMock()
            trader.place_market_order = AsyncMock(return_value=None)
            await asyncio.wait_for(start_trader(
                stop_event, combinations=[("UPBIT", "BINANCE"), ("BITHUMB", "BINANCE")],
            ), 1)
            factory.assert_called_once()
            trader.start.assert_awaited_once()
            trader.stop.assert_awaited_once()
            self.assertCountEqual(
                [call.kwargs["symbol"] for call in trader.place_market_order.await_args_list],
                ["BTC" + settings.order_quote_asset, "ETH" + settings.order_quote_asset],
            )
            self.assertTrue(all(listener.stopped.is_set() for listener in listeners))
