import logging
import unittest
from unittest.mock import patch

from src.integration.upbit_client import UpbitClient


class FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"data": {"notices": [{"id": 1, "title": "Notice"}]}}


class UpbitClientTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.scraper_url_patcher = patch(
            "src.integration.upbit_client.settings.scraper_url",
            "https://api-manager.upbit.com/api/v1/announcements/search",
        )
        self.scraper_url_patcher.start()

    def tearDown(self):
        self.scraper_url_patcher.stop()
        logging.disable(logging.NOTSET)

    @patch("src.integration.upbit_client.requests.get")
    def test_empty_search_term_uses_unfiltered_announcements_endpoint(self, get):
        get.return_value = FakeResponse()

        notices = UpbitClient().fetch_trade_notices(
            search_term="   ",
            timestamp_ms=123,
        )

        self.assertEqual(notices, [{"id": 1, "title": "Notice"}])
        self.assertEqual(
            get.call_args.args[0],
            "https://api-manager.upbit.com/api/v1/announcements",
        )
        self.assertNotIn("search", get.call_args.kwargs["params"])

    @patch("src.integration.upbit_client.requests.get")
    def test_non_empty_search_term_is_trimmed_and_sent(self, get):
        get.return_value = FakeResponse()

        UpbitClient().fetch_trade_notices(
            search_term="  KRW Market  ",
            timestamp_ms=123,
        )

        self.assertEqual(
            get.call_args.kwargs["params"]["search"],
            "KRW Market",
        )
        self.assertEqual(
            get.call_args.args[0],
            "https://api-manager.upbit.com/api/v1/announcements/search",
        )


if __name__ == "__main__":
    unittest.main()
