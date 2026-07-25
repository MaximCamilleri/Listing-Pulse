import asyncio
import logging
import time
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    NewAlgoOrderResponse,
    NewOrderResponse,
)

from src.config.settings import settings
from src.control.binance_controller import BinanceController
from src.integration.binance_integration import (
    BinanceLeverageBracket,
    BinanceMarketRules,
)
from src.support.binance_price_cache import BinancePriceCache


class FakeBinanceClient:
    def __init__(self):
        self.rules = {
            "BTCUSDT": BinanceMarketRules(
                symbol="BTCUSDT",
                status="TRADING",
                step_size=Decimal("0.1"),
                min_quantity=Decimal("0.1"),
                max_quantity=Decimal("100"),
                min_notional=Decimal("5"),
            )
        }
        self.brackets = {
            "BTCUSDT": [
                BinanceLeverageBracket(Decimal("0"), Decimal("50"), 125),
                BinanceLeverageBracket(Decimal("50"), Decimal("1000"), 75),
            ]
        }
        self.market_orders = []
        self.trailing_stop_orders = []
        self.leverage_changes = []
        self.stream_callback = None

    async def start_price_stream(self, callback):
        self.stream_callback = callback

    async def stop_price_stream(self):
        self.stream_callback = None

    async def get_market_rules(self, symbol=None):
        return self.rules

    async def get_leverage_brackets(self, symbol=None):
        return self.brackets

    async def set_initial_leverage(self, symbol, leverage):
        self.leverage_changes.append((symbol, leverage))

    async def place_market_order(self, symbol, side, quantity):
        self.market_orders.append((symbol, side, quantity))
        return NewOrderResponse(orderId=100, status="FILLED", executedQty=str(quantity))

    async def place_trailing_stop_order(
        self, symbol, side, quantity, callback_rate
    ):
        self.trailing_stop_orders.append(
            (symbol, side, quantity, callback_rate)
        )
        return NewAlgoOrderResponse(algoId=101)


class BinanceControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.original_enabled = settings.trading_enabled
        settings.trading_enabled = True

    def tearDown(self):
        settings.trading_enabled = self.original_enabled
        logging.disable(logging.NOTSET)

    async def make_controller(self, quote=Decimal("100")):
        client = FakeBinanceClient()
        cache = BinancePriceCache()
        cache.update_message({"s": "BTCUSDT", "c": "20", "E": 123})
        controller = BinanceController(quote, client, cache)
        await controller.maintain_trading_env()
        return controller, client, cache

    async def test_places_entry_and_opposite_trailing_stop_from_live_price(self):
        controller, client, _ = await self.make_controller(Decimal("30"))

        entry, stop = await controller.place_market_order(
            " btcusdt ", " buy ", Decimal("1")
        )

        self.assertEqual(entry.order_id, 100)
        self.assertEqual(stop.algo_id, 101)
        self.assertEqual(client.market_orders, [("BTCUSDT", "BUY", Decimal("1.5"))])
        self.assertEqual(
            client.trailing_stop_orders,
            [("BTCUSDT", "SELL", Decimal("1.5"), Decimal("1"))],
        )
        self.assertEqual(client.leverage_changes, [("BTCUSDT", 125)])

    async def test_reuses_confirmed_leverage(self):
        controller, client, _ = await self.make_controller()

        await controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))
        await controller.place_market_order("BTCUSDT", "SELL", Decimal("1"))

        self.assertEqual(client.leverage_changes, [("BTCUSDT", 75)])

    async def test_stale_or_missing_price_fails_before_exchange_order(self):
        now = [10.0]
        cache = BinancePriceCache(clock=lambda: now[0])
        client = FakeBinanceClient()
        controller = BinanceController(Decimal("100"), client, cache)
        await controller.maintain_trading_env()

        with self.assertRaisesRegex(RuntimeError, "No live"):
            await controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))
        cache.update_message({"s": "BTCUSDT", "c": "20"})
        now[0] += settings.binance_price_max_age_seconds + 1
        with self.assertRaisesRegex(RuntimeError, "stale"):
            await controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))
        self.assertEqual(client.market_orders, [])

    async def test_disabled_trading_makes_no_requests(self):
        settings.trading_enabled = False
        client = AsyncMock()
        controller = BinanceController(Decimal("100"), client)

        result = await controller.place_market_order(
            "BTCUSDT", "BUY", Decimal("1")
        )

        self.assertIsNone(result)
        client.place_market_order.assert_not_awaited()

    async def test_disabled_controller_start_does_not_connect_to_binance(self):
        settings.trading_enabled = False
        client = AsyncMock()
        controller = BinanceController(Decimal("100"), client)

        await controller.start()
        await controller.stop()

        client.start_price_stream.assert_not_awaited()
        client.get_market_rules.assert_not_awaited()

    async def test_validates_status_minimum_quantity_and_notional(self):
        controller, client, _ = await self.make_controller(Decimal("1"))
        with self.assertRaises(ValueError):
            await controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))

        controller.quote_amount = Decimal("100")
        client.rules["BTCUSDT"] = BinanceMarketRules(
            symbol="BTCUSDT",
            status="BREAK",
            step_size=Decimal("0.1"),
            min_quantity=Decimal("0.1"),
            max_quantity=Decimal("100"),
            min_notional=Decimal("5"),
        )
        controller.market_rules = client.rules
        with self.assertRaisesRegex(ValueError, "not trading"):
            await controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))

    async def test_missing_symbol_gets_one_refresh_then_rejection(self):
        controller, client, _ = await self.make_controller()
        client.get_market_rules = AsyncMock(return_value=client.rules)
        client.get_leverage_brackets = AsyncMock(return_value=client.brackets)

        with self.assertRaisesRegex(ValueError, "unavailable"):
            await controller.place_market_order("NEWUSDT", "BUY", Decimal("1"))

        client.get_market_rules.assert_awaited_once()
        client.get_leverage_brackets.assert_awaited_once()

    async def test_failed_leverage_change_is_not_cached(self):
        controller, client, _ = await self.make_controller()
        client.set_initial_leverage = AsyncMock(side_effect=RuntimeError("no"))

        with self.assertRaisesRegex(RuntimeError, "no"):
            await controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))

        self.assertNotIn("BTCUSDT", controller.confirmed_leverage)

    async def test_entry_rejection_invalidates_confirmed_leverage(self):
        controller, client, _ = await self.make_controller()
        controller.confirmed_leverage["BTCUSDT"] = 75
        controller._leverage_confirmed_at["BTCUSDT"] = time.monotonic()
        client.place_market_order = AsyncMock(side_effect=RuntimeError("rejected"))

        with self.assertRaisesRegex(RuntimeError, "rejected"):
            await controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))

        self.assertNotIn("BTCUSDT", controller.confirmed_leverage)

    async def test_expired_leverage_confirmation_is_reconciled(self):
        controller, client, _ = await self.make_controller()
        controller.confirmed_leverage["BTCUSDT"] = 75
        controller._leverage_confirmed_at["BTCUSDT"] = (
            time.monotonic()
            - settings.binance_leverage_reconcile_seconds
            - 1
        )

        await controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))

        self.assertEqual(client.leverage_changes, [("BTCUSDT", 75)])

    async def test_maintenance_waits_for_trade_but_price_updates_continue(self):
        controller, client, cache = await self.make_controller()
        order_started = asyncio.Event()
        release_order = asyncio.Event()

        async def slow_order(symbol, side, quantity):
            order_started.set()
            await release_order.wait()
            return NewOrderResponse(
                orderId=100, status="FILLED", executedQty=str(quantity)
            )

        client.place_market_order = slow_order
        client.get_market_rules = AsyncMock(return_value=client.rules)
        trade = asyncio.create_task(
            controller.place_market_order("BTCUSDT", "BUY", Decimal("1"))
        )
        await order_started.wait()
        refresh = asyncio.create_task(controller.maintain_trading_env())
        await asyncio.sleep(0)
        client.get_market_rules.assert_not_awaited()

        cache.update_message({"s": "BTCUSDT", "c": "21"})
        self.assertEqual(
            cache.require("BTCUSDT", settings.binance_price_max_age_seconds).price,
            Decimal("21"),
        )
        release_order.set()
        await trade
        await refresh
        client.get_market_rules.assert_awaited_once()

    async def test_create_periodically_refreshes_and_stop_closes_stream(self):
        controller, client, _ = await self.make_controller()
        controller.maintain_trading_env = AsyncMock()
        with patch.object(
            settings, "binance_env_refresh_interval_seconds", 0.01
        ):
            await controller.start()
            await asyncio.sleep(0.03)
            await controller.stop()

        self.assertGreaterEqual(controller.maintain_trading_env.await_count, 2)
        self.assertIsNone(client.stream_callback)


if __name__ == "__main__":
    unittest.main()
