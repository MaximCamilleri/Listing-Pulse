import asyncio
import logging
import threading
import unittest
from decimal import Decimal

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


if __name__ == "__main__":
    unittest.main()
