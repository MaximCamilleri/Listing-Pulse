import logging
import unittest
from decimal import Decimal

from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    NewAlgoOrderResponse,
    NewOrderResponse,
)

from control.binance_controler import BinanceService


class FakeBinanceClient:
    def __init__(self, entry_response=None, trailing_stop_response=None):
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

    def place_market_order(self, symbol, side, quantity):
        self.market_orders.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
            }
        )
        return self.entry_response

    def place_trailing_stop_order(self, symbol, side, quantity, callback_rate):
        self.trailing_stop_orders.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "callback_rate": callback_rate,
            }
        )
        return self.trailing_stop_response


class BinanceServiceTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_buy_order_places_entry_and_sell_trailing_stop(self):
        client = FakeBinanceClient()
        service = BinanceService(binance_client=client)

        entry, trailing_stop = service.place_market_order(
            symbol=" btcusdt ",
            quantity=Decimal("1.5"),
            direction=" buy ",
            callback_rate=Decimal("1.0"),
        )

        self.assertEqual(entry.order_id, 100)
        self.assertEqual(trailing_stop.algo_id, 101)
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

    def test_sell_order_places_entry_and_buy_trailing_stop(self):
        client = FakeBinanceClient()
        service = BinanceService(binance_client=client)

        service.place_market_order(
            symbol="ethusdt",
            quantity=Decimal("2"),
            direction="SELL",
            callback_rate=Decimal("0.5"),
        )

        self.assertEqual(client.market_orders[0]["side"], "SELL")
        self.assertEqual(client.trailing_stop_orders[0]["side"], "BUY")

    def test_invalid_inputs_are_rejected_before_any_exchange_call(self):
        invalid_cases = [
            {
                "symbol": "",
                "quantity": Decimal("1"),
                "direction": "BUY",
                "callback_rate": Decimal("1"),
            },
            {
                "symbol": "BTCUSDT",
                "quantity": Decimal("0"),
                "direction": "BUY",
                "callback_rate": Decimal("1"),
            },
            {
                "symbol": "BTCUSDT",
                "quantity": Decimal("1"),
                "direction": "HOLD",
                "callback_rate": Decimal("1"),
            },
            {
                "symbol": "BTCUSDT",
                "quantity": Decimal("1"),
                "direction": "BUY",
                "callback_rate": Decimal("0.09"),
            },
            {
                "symbol": "BTCUSDT",
                "quantity": Decimal("1"),
                "direction": "BUY",
                "callback_rate": Decimal("10.01"),
            },
        ]

        for kwargs in invalid_cases:
            client = FakeBinanceClient()
            service = BinanceService(binance_client=client)

            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    service.place_market_order(**kwargs)

                self.assertEqual(client.market_orders, [])
                self.assertEqual(client.trailing_stop_orders, [])

    def test_unfilled_entry_does_not_place_trailing_stop(self):
        client = FakeBinanceClient(
            entry_response=NewOrderResponse(
                orderId=100,
                status="EXPIRED",
                executedQty="0",
            )
        )
        service = BinanceService(binance_client=client)

        with self.assertRaises(RuntimeError):
            service.place_market_order(
                symbol="BTCUSDT",
                quantity=Decimal("1"),
                direction="BUY",
                callback_rate=Decimal("1"),
            )

        self.assertEqual(len(client.market_orders), 1)
        self.assertEqual(client.trailing_stop_orders, [])


if __name__ == "__main__":
    unittest.main()
