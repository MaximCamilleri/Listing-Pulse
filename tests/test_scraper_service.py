import logging
import unittest

from src.service.scraper_service import ScraperService


class FakeUpbitClient:
    def __init__(self, responses=None, exception=None):
        self.responses = list(responses or [])
        self.exception = exception
        self.calls = []

    def fetch_trade_notices(self, search_term: str, timestamp_ms: int):
        self.calls.append(
            {
                "search_term": search_term,
                "timestamp_ms": timestamp_ms,
            }
        )

        if self.exception is not None:
            raise self.exception

        if not self.responses:
            return []

        return self.responses.pop(0)


class ScraperServiceTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_initialize_seen_notices_populates_baseline(self):
        client = FakeUpbitClient(
            responses=[
                [
                    {"id": 1, "title": "Existing listing"},
                    {"id": 2, "title": "Older listing"},
                ]
            ]
        )
        service = ScraperService(upbit_client=client)

        initialized = service.initialize_seen_notices()

        self.assertTrue(initialized)
        self.assertEqual(service.seen_notices, {1, 2})
        self.assertEqual(len(client.calls), 1)

    def test_check_for_notice_skips_baseline_ids(self):
        client = FakeUpbitClient(
            responses=[
                [{"id": 1, "title": "Existing listing"}],
                [{"id": 1, "title": "Existing listing"}],
            ]
        )
        service = ScraperService(upbit_client=client)

        service.initialize_seen_notices()
        service.check_for_notice()

        self.assertEqual(service.seen_notices, {1})
        self.assertEqual(len(client.calls), 2)

    def test_check_for_notice_records_new_id_after_baseline(self):
        client = FakeUpbitClient(
            responses=[
                [{"id": 1, "title": "Existing listing"}],
                [
                    {"id": 1, "title": "Existing listing"},
                    {"id": 2, "title": "New listing"},
                ],
            ]
        )
        service = ScraperService(upbit_client=client)

        service.initialize_seen_notices()
        service.check_for_notice()

        self.assertEqual(service.seen_notices, {1, 2})

    def test_notice_without_id_is_not_recorded(self):
        client = FakeUpbitClient(
            responses=[
                [{"title": "Malformed listing"}],
                [{"title": "Still malformed"}],
            ]
        )
        service = ScraperService(upbit_client=client)

        service.initialize_seen_notices()
        service.check_for_notice()

        self.assertEqual(service.seen_notices, set())

    def test_initialize_seen_notices_failure_returns_false(self):
        client = FakeUpbitClient(exception=RuntimeError("network unavailable"))
        service = ScraperService(upbit_client=client)

        initialized = service.initialize_seen_notices()

        self.assertFalse(initialized)
        self.assertEqual(service.seen_notices, set())
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
