import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.config.settings import settings
from src.integration.telegram_integration import TelegramMessage
from src.interface.trade_interface import _trigger_action
from src.support.latency_profiler import LatencyProfiler


def make_message(date: datetime | None = None) -> TelegramMessage:
    return TelegramMessage(
        channel_id=123,
        channel_title="Listings",
        message_id=456,
        sender_id=None,
        text="notice",
        date=date or datetime.now(timezone.utc),
        has_media=False,
        grouped_id=None,
    )


class TradeInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_latency_profiler_is_forwarded_to_trade_controller(self):
        trade_control = AsyncMock()
        trade_control.place_market_order.return_value = None
        profiler = LatencyProfiler()

        with patch(
            "src.interface.trade_interface.parse_upbit_telegram_notice",
            return_value=["BTC"],
        ):
            await _trigger_action(
                make_message(),
                trade_control,
                latency_profiler=profiler,
            )

        self.assertIs(
            trade_control.place_market_order.await_args.kwargs["latency_profiler"],
            profiler,
        )
        self.assertTrue(
            any(span.name == "notice.parse_and_filter" for span in profiler.spans)
        )

    async def test_places_one_order_per_unique_asset_with_configured_quote(self):
        trade_control = AsyncMock()
        notice_date = datetime(2025, 7, 28, 12, 6, 40, tzinfo=timezone.utc)
        trade_control.place_market_order.return_value = (
            SimpleNamespace(update_time=int(notice_date.timestamp() * 1_000) + 1_500),
            SimpleNamespace(),
        )

        with (
            patch(
                "src.interface.trade_interface.parse_upbit_telegram_notice",
                return_value=["BTC", "ETH", "BTC"],
            ),
            patch.object(settings, "order_quote_asset", "USDC"),
        ):
            await _trigger_action(make_message(notice_date), trade_control)

        self.assertEqual(trade_control.place_market_order.await_count, 2)
        self.assertEqual(
            [call.kwargs["symbol"] for call in trade_control.place_market_order.await_args_list],
            ["BTCUSDC", "ETHUSDC"],
        )

    async def test_logs_notice_to_order_open_latency_for_each_opened_order(self):
        trade_control = AsyncMock()
        notice_date = datetime(2025, 7, 28, 12, 6, 40, tzinfo=timezone.utc)
        trade_control.place_market_order.return_value = (
            SimpleNamespace(update_time=int(notice_date.timestamp() * 1_000) + 1_500),
            SimpleNamespace(),
        )
        message = make_message(notice_date)

        with (
            patch(
                "src.interface.trade_interface.parse_upbit_telegram_notice",
                return_value=["BTC"],
            ),
            self.assertLogs("src.interface.trade_interface", level="INFO") as logs,
        ):
            await _trigger_action(message, trade_control)

        latency_log = next(
            record for record in logs.output if "Opened order from Telegram notice" in record
        )
        self.assertIn("symbol=BTCUSDT", latency_log)
        self.assertIn("channel_id=123", latency_log)
        self.assertIn("message_id=456", latency_log)
        self.assertIn("latency_seconds=1.500", latency_log)

    async def test_irrelevant_notice_does_not_place_order(self):
        trade_control = AsyncMock()

        with patch(
            "src.interface.trade_interface.parse_upbit_telegram_notice",
            return_value=[],
        ):
            await _trigger_action(make_message(), trade_control)

        trade_control.place_market_order.assert_not_awaited()

    async def test_order_failure_is_propagated(self):
        trade_control = AsyncMock()
        trade_control.place_market_order.side_effect = RuntimeError("order failed")

        with patch(
            "src.interface.trade_interface.parse_upbit_telegram_notice",
            return_value=["BTC"],
        ):
            with self.assertRaisesRegex(RuntimeError, "order failed"):
                await _trigger_action(make_message(), trade_control)

    async def test_disabled_trade_does_not_log_order_opened(self):
        trade_control = AsyncMock()
        trade_control.place_market_order.return_value = None

        with (
            patch(
                "src.interface.trade_interface.parse_upbit_telegram_notice",
                return_value=["BTC"],
            ),
            self.assertLogs("src.interface.trade_interface", level="INFO") as logs,
        ):
            await _trigger_action(make_message(), trade_control)

        self.assertFalse(
            any("Opened order from Telegram notice" in record for record in logs.output)
        )


if __name__ == "__main__":
    unittest.main()
