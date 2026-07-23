import logging
import unittest
from decimal import Decimal

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


class FakeBinanceClient:
    def __init__(
        self,
        entry_response=None,
        trailing_stop_response=None,
        *,
        price=Decimal("20"),
        market_rules=None,
        leverage_brackets=None,
    ):
        self.entry_response = entry_response or NewOrderResponse(
            orderId=100,
            status="FILLED",
            executedQty="1.5",
        )
        self.trailing_stop_response = (
            trailing_stop_response or NewAlgoOrderResponse(algoId=101)
        )
        self.market_orders = []
        self.trailing_stop_orders = []
        self.price = price
        self.market_rules = market_rules or BinanceMarketRules(
            symbol="BTCUSDT",
            status="TRADING",
            step_size=Decimal("0.1"),
            min_quantity=Decimal("0.1"),
            max_quantity=Decimal("100"),
            min_notional=Decimal("5"),
        )
        self.leverage_brackets = leverage_brackets or [
            BinanceLeverageBracket(
                notional_floor=Decimal("0"),
                notional_cap=Decimal("1000"),
                initial_leverage=125,
            )
        ]
        self.leverage_changes = []

    async def get_market_rules(self, symbol):
        return self.market_rules

    async def get_symbol_price(self, symbol):
        return self.price

    async def get_leverage_brackets(self, symbol):
        return self.leverage_brackets

    async def set_initial_leverage(self, symbol, leverage):
        self.leverage_changes.append({"symbol": symbol, "leverage": leverage})

    async def place_market_order(self, symbol, side, quantity):
        self.market_orders.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
            }
        )
        return self.entry_response

    async def place_trailing_stop_order(self, symbol, side, quantity, callback_rate):
        self.trailing_stop_orders.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "callback_rate": callback_rate,
            }
        )
        return self.trailing_stop_response


class BinanceControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.original_trading_enabled = settings.trading_enabled
        settings.trading_enabled = True

    def tearDown(self):
        settings.trading_enabled = self.original_trading_enabled
        logging.disable(logging.NOTSET)

    async def test_buy_order_places_entry_and_sell_trailing_stop(self):
        client = FakeBinanceClient()
        service = BinanceController(binance_client=client)

        entry, trailing_stop = await service.place_market_order(
            symbol=" btcusdt ",
            quote_amount=Decimal("30"),
            direction=" buy ",
            callback_rate=Decimal("1.0"),
        )

        self.assertEqual(entry.order_id, 100)
        self.assertEqual(trailing_stop.algo_id, 101)
        self.assertEqual(
            client.leverage_changes,
            [{"symbol": "BTCUSDT", "leverage": 125}],
        )
        self.assertEqual(
            client.market_orders,
            [
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "quantity": Decimal("1.5"),
                }
            ],
        )
        self.assertEqual(
            client.trailing_stop_orders,
            [
                {
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "quantity": Decimal("1.5"),
                    "callback_rate": Decimal("1.0"),
                }
            ],
        )

    async def test_sell_order_places_entry_and_buy_trailing_stop(self):
        client = FakeBinanceClient()
        service = BinanceController(binance_client=client)

        await service.place_market_order(
            symbol="ethusdt",
            quote_amount=Decimal("40"),
            direction="SELL",
            callback_rate=Decimal("0.5"),
        )

        self.assertEqual(client.market_orders[0]["side"], "SELL")
        self.assertEqual(client.trailing_stop_orders[0]["side"], "BUY")

    async def test_invalid_inputs_are_rejected_before_any_exchange_call(self):
        invalid_cases = [
            {
                "symbol": "",
                "quote_amount": Decimal("1"),
                "direction": "BUY",
                "callback_rate": Decimal("1"),
            },
            {
                "symbol": "BTCUSDT",
                "quote_amount": Decimal("0"),
                "direction": "BUY",
                "callback_rate": Decimal("1"),
            },
            {
                "symbol": "BTCUSDT",
                "quote_amount": Decimal("1"),
                "direction": "HOLD",
                "callback_rate": Decimal("1"),
            },
            {
                "symbol": "BTCUSDT",
                "quote_amount": Decimal("1"),
                "direction": "BUY",
                "callback_rate": Decimal("0.09"),
            },
            {
                "symbol": "BTCUSDT",
                "quote_amount": Decimal("1"),
                "direction": "BUY",
                "callback_rate": Decimal("10.01"),
            },
        ]

        for kwargs in invalid_cases:
            client = FakeBinanceClient()
            service = BinanceController(binance_client=client)

            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    await service.place_market_order(**kwargs)

                self.assertEqual(client.market_orders, [])
                self.assertEqual(client.trailing_stop_orders, [])

    async def test_unfilled_entry_does_not_place_trailing_stop(self):
        client = FakeBinanceClient(
            entry_response=NewOrderResponse(
                orderId=100,
                status="EXPIRED",
                executedQty="0",
            )
        )
        service = BinanceController(binance_client=client)

        with self.assertRaises(RuntimeError):
            await service.place_market_order(
                symbol="BTCUSDT",
                quote_amount=Decimal("20"),
                direction="BUY",
                callback_rate=Decimal("1"),
            )

        self.assertEqual(len(client.market_orders), 1)
        self.assertEqual(client.trailing_stop_orders, [])

    async def test_quote_amount_is_rounded_down_to_market_step_size(self):
        client = FakeBinanceClient(
            price=Decimal("3"),
            market_rules=BinanceMarketRules(
                symbol="SOONUSDT",
                status="TRADING",
                step_size=Decimal("0.1"),
                min_quantity=Decimal("0.1"),
                max_quantity=Decimal("10000"),
                min_notional=Decimal("5"),
            ),
        )
        service = BinanceController(binance_client=client)

        await service.place_market_order(
            symbol="SOONUSDT",
            quote_amount=Decimal("100"),
            direction="BUY",
            callback_rate=Decimal("1"),
        )

        self.assertEqual(
            client.market_orders[0]["quantity"],
            Decimal("33.3"),
        )
        self.assertLessEqual(
            client.market_orders[0]["quantity"] * client.price,
            Decimal("100"),
        )

    async def test_uses_highest_leverage_for_matching_notional_bracket(self):
        client = FakeBinanceClient(
            leverage_brackets=[
                BinanceLeverageBracket(
                    notional_floor=Decimal("0"),
                    notional_cap=Decimal("50"),
                    initial_leverage=125,
                ),
                BinanceLeverageBracket(
                    notional_floor=Decimal("50"),
                    notional_cap=Decimal("1000"),
                    initial_leverage=75,
                ),
            ]
        )
        service = BinanceController(binance_client=client)

        await service.place_market_order(
            symbol="BTCUSDT",
            quote_amount=Decimal("100"),
            direction="BUY",
            callback_rate=Decimal("1"),
        )

        self.assertEqual(
            client.leverage_changes,
            [{"symbol": "BTCUSDT", "leverage": 75}],
        )


if __name__ == "__main__":
    unittest.main()
