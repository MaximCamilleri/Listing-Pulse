import asyncio
import logging
import threading
import unittest
from decimal import Decimal
from types import SimpleNamespace

from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    NewAlgoOrderResponse,
    NewOrderResponse,
)

from src.integration.binance_integration import BinanceIntegration


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def data(self):
        return self.payload


class FakeRestApi:
    def __init__(self):
        self.new_order_calls = []
        self.new_algo_order_calls = []
        self.leverage_calls = []

    def new_order(self, **kwargs):
        self.new_order_calls.append(kwargs)
        return FakeResponse(
            NewOrderResponse(
                orderId=200,
                status="FILLED",
                executedQty="1.25",
            )
        )

    def new_algo_order(self, **kwargs):
        self.new_algo_order_calls.append(kwargs)
        return FakeResponse(NewAlgoOrderResponse(algoId=201))

    def exchange_information(self):
        return FakeResponse(
            SimpleNamespace(
                symbols=[
                    SimpleNamespace(
                        symbol="SOONUSDT",
                        status="TRADING",
                        filters=[
                            SimpleNamespace(
                                filter_type="MARKET_LOT_SIZE",
                                step_size="1",
                                min_qty="1",
                                max_qty="1000000",
                                notional=None,
                            ),
                            SimpleNamespace(
                                filter_type="MIN_NOTIONAL",
                                step_size=None,
                                min_qty=None,
                                max_qty=None,
                                notional="5",
                            ),
                        ],
                    )
                ]
            )
        )

    def symbol_price_ticker_v2(self, symbol):
        return FakeResponse(
            SimpleNamespace(
                actual_instance=SimpleNamespace(symbol=symbol, price="0.50")
            )
        )

    def notional_and_leverage_brackets(self, symbol):
        return FakeResponse(
            SimpleNamespace(
                actual_instance=SimpleNamespace(
                    symbol=symbol,
                    brackets=[
                        SimpleNamespace(
                            notional_floor=0,
                            notional_cap=50000,
                            initial_leverage=75,
                        )
                    ],
                )
            )
        )

    def change_initial_leverage(self, symbol, leverage):
        self.leverage_calls.append(
            {"symbol": symbol, "leverage": leverage}
        )
        return FakeResponse(SimpleNamespace(symbol=symbol, leverage=leverage))


class BlockingRestApi(FakeRestApi):
    def __init__(self, release_request):
        super().__init__()
        self.release_request = release_request
        self.request_started = threading.Event()

    def new_order(self, **kwargs):
        self.request_started.set()
        self.release_request.wait(timeout=1)
        return super().new_order(**kwargs)


class FakeSdkClient:
    def __init__(self):
        self.rest_api = FakeRestApi()


class FakeStreamHandle:
    def __init__(self, calls):
        self.calls = calls

    def on(self, event, callback):
        self.calls.append(("on", event, callback))

    async def unsubscribe(self):
        self.calls.append(("unsubscribe",))


class FakeWebSocketStreams:
    def __init__(self):
        self.calls = []
        self.handle = FakeStreamHandle(self.calls)

    async def create_connection(self):
        self.calls.append(("create_connection",))

    async def all_market_tickers_streams(self):
        self.calls.append(("subscribe_all_market_tickers",))
        return self.handle

    async def close_connection(self, close_session=True):
        self.calls.append(("close_connection", close_session))


class FakeStreamingSdkClient(FakeSdkClient):
    def __init__(self):
        super().__init__()
        self.websocket_streams = FakeWebSocketStreams()


class BinanceClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    async def test_place_market_order_submits_expected_sdk_parameters(self):
        client = BinanceIntegration.__new__(BinanceIntegration)
        client.client = FakeSdkClient()

        response = await client.place_market_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity=Decimal("1.25"),
        )

        self.assertEqual(response.order_id, 200)
        self.assertEqual(response.status, "FILLED")
        self.assertEqual(
            client.client.rest_api.new_order_calls,
            [
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": 1.25,
                    "reduce_only": False,
                    "new_order_resp_type": "RESULT",
                }
            ],
        )

    async def test_connects_before_subscribing_to_price_stream(self):
        client = BinanceIntegration.__new__(BinanceIntegration)
        client.client = FakeStreamingSdkClient()
        client._price_stream_handle = None
        callback = lambda message: None

        await client.start_price_stream(callback)
        await client.stop_price_stream()

        self.assertEqual(
            client.client.websocket_streams.calls,
            [
                ("create_connection",),
                ("subscribe_all_market_tickers",),
                ("on", "message", callback),
                ("unsubscribe",),
                ("close_connection", True),
            ],
        )

    async def test_place_trailing_stop_order_submits_expected_sdk_parameters(self):
        client = BinanceIntegration.__new__(BinanceIntegration)
        client.client = FakeSdkClient()

        response = await client.place_trailing_stop_order(
            symbol="BTCUSDT",
            side="SELL",
            quantity=Decimal("1.25"),
            callback_rate=Decimal("1.5"),
        )

        self.assertEqual(response.algo_id, 201)
        self.assertEqual(
            client.client.rest_api.new_algo_order_calls,
            [
                {
                    "algo_type": "CONDITIONAL",
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "type": "TRAILING_STOP_MARKET",
                    "quantity": 1.25,
                    "callback_rate": 1.5,
                    "reduce_only": True,
                    "working_type": "MARK_PRICE",
                    "new_order_resp_type": "RESULT",
                }
            ],
        )

    async def test_market_order_does_not_block_event_loop(self):
        release_request = threading.Event()
        rest_api = BlockingRestApi(release_request)
        client = BinanceIntegration.__new__(BinanceIntegration)
        client.client = FakeSdkClient()
        client.client.rest_api = rest_api

        order_task = asyncio.create_task(
            client.place_market_order("BTCUSDT", "BUY", Decimal("1"))
        )
        try:
            request_started = await asyncio.to_thread(
                rest_api.request_started.wait,
                1,
            )
            self.assertTrue(request_started)
            await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)
        finally:
            release_request.set()

        await order_task

    async def test_returns_market_sizing_rules(self):
        client = BinanceIntegration.__new__(BinanceIntegration)
        client.client = FakeSdkClient()

        rules = (await client.get_market_rules("SOONUSDT"))["SOONUSDT"]

        self.assertEqual(rules.symbol, "SOONUSDT")
        self.assertEqual(rules.status, "TRADING")
        self.assertEqual(rules.step_size, Decimal("1"))
        self.assertEqual(rules.min_quantity, Decimal("1"))
        self.assertEqual(rules.max_quantity, Decimal("1000000"))
        self.assertEqual(rules.min_notional, Decimal("5"))

    async def test_returns_symbol_price_and_leverage_brackets(self):
        client = BinanceIntegration.__new__(BinanceIntegration)
        client.client = FakeSdkClient()

        price = (await client.get_symbol_price("SOONUSDT"))["SOONUSDT"]
        brackets = (await client.get_leverage_brackets("SOONUSDT"))["SOONUSDT"]

        self.assertEqual(price, Decimal("0.50"))
        self.assertEqual(len(brackets), 1)
        self.assertEqual(brackets[0].initial_leverage, 75)
        self.assertEqual(brackets[0].notional_cap, Decimal("50000"))

    async def test_selects_symbol_from_list_leverage_response(self):
        client = BinanceIntegration.__new__(BinanceIntegration)
        client.client = FakeSdkClient()
        other_symbol = SimpleNamespace(
            symbol="BTCUSDT",
            brackets=[
                SimpleNamespace(
                    notional_floor=0,
                    notional_cap=50000,
                    initial_leverage=125,
                )
            ],
        )
        target_symbol = SimpleNamespace(
            symbol="SOONUSDT",
            brackets=[
                SimpleNamespace(
                    notional_floor=0,
                    notional_cap=10000,
                    initial_leverage=50,
                )
            ],
        )
        client.client.rest_api.notional_and_leverage_brackets = (
            lambda symbol: FakeResponse(
                SimpleNamespace(actual_instance=[other_symbol, target_symbol])
            )
        )

        brackets = (await client.get_leverage_brackets("SOONUSDT"))["SOONUSDT"]

        self.assertEqual(len(brackets), 1)
        self.assertEqual(brackets[0].initial_leverage, 50)
        self.assertEqual(brackets[0].notional_cap, Decimal("10000"))

    async def test_sets_initial_leverage(self):
        client = BinanceIntegration.__new__(BinanceIntegration)
        client.client = FakeSdkClient()

        await client.set_initial_leverage("SOONUSDT", 75)

        self.assertEqual(
            client.client.rest_api.leverage_calls,
            [{"symbol": "SOONUSDT", "leverage": 75}],
        )


if __name__ == "__main__":
    unittest.main()
