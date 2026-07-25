import unittest
from decimal import Decimal

from src.support.binance_price_cache import BinancePriceCache


class BinancePriceCacheTests(unittest.TestCase):
    def test_parses_dictionary_and_model_shaped_messages(self):
        cache = BinancePriceCache(clock=lambda: 5.0)
        cache.update_message(
            [
                {"s": "BTCUSDT", "c": "10.5", "E": 100},
                type("Ticker", (), {"s": "ETHUSDT", "c": "20", "E": 101})(),
            ]
        )

        self.assertEqual(cache.require("BTCUSDT", 1).price, Decimal("10.5"))
        self.assertEqual(cache.require("ETHUSDT", 1).exchange_time_ms, 101)

    def test_ignores_incomplete_and_non_positive_prices(self):
        cache = BinancePriceCache()
        cache.update_message([{"s": "BTCUSDT"}, {"s": "ETHUSDT", "c": "0"}])

        with self.assertRaises(RuntimeError):
            cache.require("BTCUSDT", 1)
        with self.assertRaises(RuntimeError):
            cache.require("ETHUSDT", 1)


if __name__ == "__main__":
    unittest.main()
