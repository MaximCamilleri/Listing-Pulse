import logging
import threading
import unittest

from src.control.scraper_service import ScraperService


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
        poll_successes = []
        client = FakeUpbitClient(
            responses=[
                [
                    {"id": 1, "title": "Existing listing"},
                    {"id": 2, "title": "Older listing"},
                ]
            ]
        )
        service = ScraperService(
            upbit_client=client,
            poll_success_recorder=lambda: poll_successes.append(True),
        )

        initialized = service.initialize_seen_notices()

        self.assertTrue(initialized)
        self.assertEqual(service.seen_notices, {1, 2})
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(poll_successes, [True])

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
        poll_successes = []
        client = FakeUpbitClient(exception=RuntimeError("network unavailable"))
        service = ScraperService(
            upbit_client=client,
            poll_success_recorder=lambda: poll_successes.append(True),
        )

        initialized = service.initialize_seen_notices()

        self.assertFalse(initialized)
        self.assertEqual(service.seen_notices, set())
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(poll_successes, [])

    def test_check_for_notice_records_successful_poll(self):
        poll_successes = []
        service = ScraperService(
            upbit_client=FakeUpbitClient(responses=[[]]),
            poll_success_recorder=lambda: poll_successes.append(True),
        )

        service.check_for_notice()

        self.assertEqual(poll_successes, [True])

    def test_new_notice_calls_handler(self):
        client = FakeUpbitClient(
            responses=[
                [],
                [{"id": 10, "title": "New KRW Market listing (ABC)"}],
            ]
        )
        handled_notices = []
        service = ScraperService(
            upbit_client=client,
            on_new_notice=handled_notices.append,
        )

        service.initialize_seen_notices()
        service.check_for_notice()

        self.assertEqual(service.seen_notices, {10})
        self.assertEqual(
            handled_notices,
            [{"id": 10, "title": "New KRW Market listing (ABC)"}],
        )

    def test_seen_notice_does_not_call_handler(self):
        client = FakeUpbitClient(
            responses=[
                [{"id": 10, "title": "Existing listing"}],
                [{"id": 10, "title": "Existing listing"}],
            ]
        )
        handled_notices = []
        service = ScraperService(
            upbit_client=client,
            on_new_notice=handled_notices.append,
        )

        service.initialize_seen_notices()
        service.check_for_notice()

        self.assertEqual(handled_notices, [])

    def test_sleep_returns_when_stop_event_is_set(self):
        stop_event = threading.Event()
        service = ScraperService(
            upbit_client=FakeUpbitClient(),
            stop_event=stop_event,
        )
        stop_event.set()

        service._sleep(60)

        self.assertTrue(stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
