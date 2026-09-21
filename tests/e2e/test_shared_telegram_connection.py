import asyncio
import threading
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from src.config.settings import settings
from src.interface.trade_interface import start_trader


class SharedTelegramConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_client_routes_both_channels_across_reconnect_and_drains(self):
        stop_event = threading.Event()
        disconnected = asyncio.Event()
        other_channel_processed = asyncio.Event()
        handlers = []
        completed = []
        connection_rounds = 0
        connected = False
        client = Mock()

        async def connect(**kwargs):
            nonlocal connected
            connected = True

        async def disconnect():
            nonlocal connected
            connected = False
            disconnected.set()

        async def deliver(channel, text, message_id):
            event = SimpleNamespace(
                chat_id=channel,
                get_chat=AsyncMock(return_value=SimpleNamespace(title="Listings")),
                message=SimpleNamespace(
                    id=message_id, sender_id=1, raw_text=text, out=False,
                    date=datetime.now(timezone.utc), media=None, grouped_id=None,
                ),
            )
            for callback, builder in handlers:
                await builder.resolve(client)
                if builder.filter(event):
                    await callback(event)

        async def receive():
            nonlocal connection_rounds, connected
            connection_rounds += 1
            self.assertEqual(len(handlers), 2)
            await deliver(-1000000000001, "[거래] 비트코인(BTC) 신규 거래지원 안내 (KRW)", connection_rounds)
            await deliver(-1000000000002, "[마켓 추가] 이더리움(ETH) 원화 마켓 추가 안내", connection_rounds)
            # A third channel must never reach either parser.
            await deliver(-1000000000003, "[거래] 솔라나(SOL) 신규 거래지원 안내 (KRW)", connection_rounds)
            if connection_rounds == 1:
                connected = False
                return
            stop_event.set()
            await disconnected.wait()

        async def place_order(**kwargs):
            symbol = kwargs["symbol"]
            if symbol.startswith("BTC"):
                # A slow Upbit action must not block Bithumb's worker.
                await asyncio.wait_for(other_channel_processed.wait(), 1)
            else:
                other_channel_processed.set()
            await asyncio.sleep(0.01)
            completed.append(symbol)

        client.start = AsyncMock(side_effect=connect)
        client.is_connected.side_effect = lambda: connected
        client.disconnect = AsyncMock(side_effect=disconnect)
        client.run_until_disconnected = AsyncMock(side_effect=receive)
        client.add_event_handler.side_effect = lambda callback, builder: handlers.append((callback, builder))
        client.remove_event_handler.side_effect = lambda callback, builder: handlers.remove((callback, builder))

        with (
            patch("src.integration.telegram_integration.StringSession"),
            patch("src.integration.telegram_integration.TelegramClient", return_value=client) as factory,
            patch("src.integration.telegram_integration.record_health"),
            patch("src.control.event_to_trade.BinanceController") as trade_factory,
            patch.object(settings, "telegram_session", "fake-session"),
            patch.object(settings, "telegram_api_hash", "fake-hash"),
            patch.object(settings, "upbit_telegram_channel", "-1000000000001"),
            patch.object(settings, "bithumb_telegram_channel", "-1000000000002"),
            patch.object(settings, "telegram_supervisor_initial_delay", 0.001),
        ):
            trader = trade_factory.return_value
            trader.start = AsyncMock()
            trader.place_market_order = AsyncMock(side_effect=place_order)

            async def stop_trader():
                self.assertFalse(connected)
                self.assertEqual(len(completed), 4)
                self.assertEqual(handlers, [])

            trader.stop = AsyncMock(side_effect=stop_trader)
            await asyncio.wait_for(start_trader(
                stop_event, combinations=[("UPBIT", "BINANCE"), ("BITHUMB", "BINANCE")],
            ), 2)
            factory.assert_called_once()
            trade_factory.assert_called_once()
            trader.start.assert_awaited_once()
            trader.stop.assert_awaited_once()
            client.disconnect.assert_awaited_once()
            self.assertEqual(client.start.await_count, 2)
            self.assertEqual(client.add_event_handler.call_count, 2)
            self.assertCountEqual(completed, ["BTC" + settings.order_quote_asset, "ETH" + settings.order_quote_asset] * 2)
