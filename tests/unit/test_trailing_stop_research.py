import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from research.util.binance_tick_feed import Tick
from research.util.binance_tick_feed import (
    DEFAULT_CACHE_DIRECTORY,
    BinanceTickFeed,
    REST_WINDOW_MS,
)
from research.util.trailing_stop import (
    calculate_trailing_stop_pnl,
    normalize_symbol,
    simulate_trailing_stop,
    timestamp_to_ms,
)


class FakeTickFeed:
    def __init__(self, ticks):
        self.ticks = ticks
        self.request = None

    def iter_ticks(self, symbol, start_time_ms, end_time_ms):
        self.request = (symbol, start_time_ms, end_time_ms)
        return iter(self.ticks)


class TrailingStopResearchTests(unittest.TestCase):
    def test_calculates_pnl_at_first_tick_below_trailing_stop(self):
        ticks = [
            Tick(1, 100.0, 1.0, 1_000),
            Tick(2, 120.0, 1.0, 1_001),
            Tick(3, 115.0, 1.0, 1_002),
            Tick(4, 108.0, 1.0, 1_003),
            Tick(5, 130.0, 1.0, 1_004),
        ]

        pnl = calculate_trailing_stop_pnl(ticks, 10)

        self.assertAlmostEqual(pnl, 8.0)

    def test_public_function_normalizes_symbol_and_bounds_replay(self):
        feed = FakeTickFeed([Tick(1, 100.0, 1.0, 1_000), Tick(2, 90.0, 1.0, 1_001)])

        pnl = simulate_trailing_stop(" btc ", 1_000, 5, tick_feed=feed, max_hold_ms=500)

        self.assertAlmostEqual(pnl, -10.0)
        self.assertEqual(feed.request, ("BTCUSDT", 1_000, 1_500))

    def test_raises_when_stop_does_not_trigger(self):
        ticks = [Tick(1, 100.0, 1.0, 1_000), Tick(2, 110.0, 1.0, 1_001)]

        with self.assertRaisesRegex(RuntimeError, "not triggered"):
            calculate_trailing_stop_pnl(ticks, 5)

    def test_accepts_timezone_aware_datetime(self):
        value = datetime(1970, 1, 1, 0, 0, 1, 123000, tzinfo=timezone.utc)

        self.assertEqual(timestamp_to_ms(value), 1_123)

    def test_validates_inputs(self):
        self.assertEqual(normalize_symbol("ethusdt"), "ETHUSDT")
        with self.assertRaises(ValueError):
            normalize_symbol(" ")
        with self.assertRaises(ValueError):
            calculate_trailing_stop_pnl([], 0)
        with self.assertRaises(ValueError):
            timestamp_to_ms(datetime(2025, 1, 1))


class BinanceTickFeedTests(unittest.TestCase):
    def test_default_cache_is_anchored_to_research_data(self):
        feed = BinanceTickFeed()

        self.assertEqual(feed.cache_directory, DEFAULT_CACHE_DIRECTORY)
        self.assertEqual(feed.cache_directory.name, "binance")
        self.assertEqual(feed.cache_directory.parent.name, "data")
        self.assertEqual(feed.cache_directory.parent.parent.name, "research")

    @patch("research.util.binance_tick_feed.datetime")
    def test_old_time_range_uses_archive(self, datetime_mock):
        datetime_mock.now.return_value = datetime(2026, 7, 19, tzinfo=timezone.utc)
        feed = BinanceTickFeed()
        expected = [Tick(1, 100.0, 1.0, 1_000)]
        feed._iter_archive_ticks = lambda *args: iter(expected)

        self.assertEqual(list(feed.iter_ticks("BTCUSDT", 1_000, 2_000)), expected)

    def test_recent_rest_requests_are_less_than_one_hour(self):
        feed = BinanceTickFeed()
        requests = []

        def fake_get_json(path, query):
            requests.append(query)
            return []

        feed._get_json = fake_get_json
        list(feed._iter_rest_ticks("BTCUSDT", 1_000, 1_000 + REST_WINDOW_MS + 1))

        self.assertEqual(len(requests), 2)
        self.assertLess(requests[0]["endTime"] - requests[0]["startTime"], 60 * 60 * 1000)


if __name__ == "__main__":
    unittest.main()
