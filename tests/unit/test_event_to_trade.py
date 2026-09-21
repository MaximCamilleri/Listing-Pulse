import asyncio
import threading
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from src.config.settings import settings
from src.control.event_to_trade import EventToTrade
from src.interface.trade_interface import start_trader
from test_trade_interface import make_message


class EventToTradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_sources_wire_matching_channel_and_parser_without_starting(self):
        for source, channel_setting, parser in (
            ("UPBIT", "upbit_telegram_channel", "parse_upbit_telegram_notice"),
            ("BITHUMB", "bithumb_telegram_channel", "parse_bithumb_telegram_notice"),
        ):
            with (
                self.subTest(source=source),
                patch("src.control.event.listener_factory.TelegramController") as listener,
                patch("src.control.event_to_trade.BinanceController") as trader,
                patch(f"src.control.event_to_trade.{parser}", return_value=["BTC"]) as parse,
                patch.object(settings, channel_setting, "test-channel"),
            ):
                trader.return_value.place_market_order = AsyncMock(return_value=None)
                workflow = EventToTrade(source, "BINANCE")
                trader.return_value.start.assert_not_called()
                listener.return_value.run.assert_not_called()
                self.assertEqual(listener.call_args.kwargs["channel"], "test-channel")
                message = make_message()
                await listener.call_args.kwargs["message_handler"](message)
                parse.assert_called_once_with(message)
                workflow.trade_control.place_market_order.assert_awaited_once()

    async def test_invalid_sources_fail_before_creating_controllers(self):
        with patch("src.control.event_to_trade.BinanceController") as trader:
            for event_source, trade_source in (("UNKNOWN", "BINANCE"), ("UPBIT", "")):
                with self.assertRaises(ValueError):
                    EventToTrade(event_source, trade_source)
            trader.assert_not_called()

    async def test_bithumb_notice_trades_unique_krw_symbols_only(self):
        with patch("src.control.event.listener_factory.TelegramController"):
            trader = AsyncMock()
            trader.place_market_order.return_value = None
            workflow = EventToTrade("BITHUMB", "BINANCE", trade_control=trader)
            for text in (
                "[마켓 추가] 비트코인(BTC) USDT 마켓 추가 안내",
                "unrelated message",
            ):
                await workflow.trigger_action(replace(make_message(), text=text))
            trader.place_market_order.assert_not_awaited()
            await workflow.trigger_action(replace(
                make_message(),
                text="[마켓 추가] 비트코인(BTC), 이더리움(ETH), 비트코인(BTC) 원화 마켓 추가 안내",
            ))
            self.assertEqual(
                [call.kwargs["symbol"] for call in trader.place_market_order.await_args_list],
                ["BTC" + settings.order_quote_asset, "ETH" + settings.order_quote_asset],
            )

    async def test_custom_handler_is_wired(self):
        with patch("src.control.event.listener_factory.TelegramController") as listener:
            handler = AsyncMock()
            EventToTrade("UPBIT", "BINANCE", trade_control=AsyncMock(), message_handler=handler)
            self.assertIs(listener.call_args.kwargs["message_handler"], handler)


class TraderLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_stops_listener_before_trader(self):
        stopped = asyncio.Event()
        stop_event = threading.Event()
        events = []

        async def run_listener():
            events.append("listener-start")
            stop_event.set()
            await stopped.wait()

        async def stop_listener():
            events.append("listener-stop")
            stopped.set()

        with patch("src.interface.trade_interface.EventToTrade") as compose:
            workflow = compose.return_value
            workflow.trade_control = AsyncMock()
            workflow.event_control = AsyncMock()
            workflow.event_control.run.side_effect = run_listener
            workflow.event_control.stop.side_effect = stop_listener
            workflow.trade_control.stop.side_effect = lambda: events.append("trader-stop")
            await asyncio.wait_for(start_trader(stop_event), timeout=1)
            workflow.trade_control.start.assert_awaited_once()
            workflow.trade_control.stop.assert_awaited_once()
            self.assertLess(events.index("listener-stop"), events.index("trader-stop"))

    async def test_startup_failure_cleans_up_trade_controller(self):
        with patch("src.interface.trade_interface.EventToTrade") as compose:
            workflow = compose.return_value
            workflow.trade_control = AsyncMock()
            workflow.event_control = AsyncMock()
            workflow.trade_control.start.side_effect = RuntimeError("startup failed")
            with self.assertLogs("src.interface.trade_interface", level="ERROR"):
                with self.assertRaisesRegex(RuntimeError, "startup failed"):
                    await start_trader()
            workflow.event_control.run.assert_not_awaited()
            workflow.trade_control.stop.assert_awaited_once()
