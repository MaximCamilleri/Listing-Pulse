import random
import time
from typing import Any

from src.config.settings import settings
from src.integration.upbit_client import UpbitClient


class ScraperService:
    def __init__(self, upbit_client: UpbitClient | None = None) -> None:
        self.upbit_client = upbit_client or UpbitClient()
        self.seen_notices: set[Any] = set()

    def start(self) -> None:
        while True:
            self.check_for_notice()

            sleep_time = random.uniform(
                settings.scraper_cooldown - settings.scraper_cooldown_offset,
                settings.scraper_cooldown + settings.scraper_cooldown_offset,
            )
            time.sleep(sleep_time)

    def check_for_notice(self) -> None:
        try:
            notices = self.upbit_client.fetch_trade_notices(
                search_term=settings.scraper_search_term,
                timestamp_ms=int(time.time() * 1000),
            )
            print(f"Ping: {time.time()}, KRW results: {len(notices)}")

            for notice in notices:
                notice_id = notice.get("id")
                title = notice.get("title", "")

                if notice_id in self.seen_notices:
                    continue

                if settings.scraper_search_term.upper() in title.upper():
                    print(f"New KRW Listing: {title}, Time: {notice.get('listed_at')}")

                self.seen_notices.add(notice_id)

        except Exception as e:
            print(f"Network error: {e}")
