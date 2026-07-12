import random
import time
from typing import Any

from src.config.settings import settings
from src.integration.upbit_client import UpbitClient
from src.support.logger import get_logger


logger = get_logger(__name__)


class ScraperService:
    def __init__(self, upbit_client: UpbitClient | None = None) -> None:
        self.upbit_client = upbit_client or UpbitClient()
        self.seen_notices: set[Any] = set()
        logger.debug("ScraperService initialized")

    def start(self) -> None:
        logger.info(
            "Starting scraper loop search_term=%s cooldown_seconds=%.2f offset_seconds=%.2f",
            settings.scraper_search_term,
            settings.scraper_cooldown,
            settings.scraper_cooldown_offset,
        )
        while True:
            self.check_for_notice()

            sleep_time = random.uniform(
                settings.scraper_cooldown - settings.scraper_cooldown_offset,
                settings.scraper_cooldown + settings.scraper_cooldown_offset,
            )
            logger.debug(
                "Sleeping before next scraper check sleep_seconds=%.2f",
                sleep_time,
            )
            time.sleep(sleep_time)

    def check_for_notice(self) -> None:
        try:
            checked_at = time.time()
            notices = self.upbit_client.fetch_trade_notices(
                search_term=settings.scraper_search_term,
                timestamp_ms=int(checked_at * 1000),
            )
            logger.info(
                "Fetched Upbit trade notices result_count=%d seen_notice_count=%d",
                len(notices),
                len(self.seen_notices),
            )

            for notice in notices:
                notice_id = notice.get("id")
                title = notice.get("title", "")

                if notice_id in self.seen_notices:
                    logger.debug(
                        "Skipping previously seen notice notice_id=%s",
                        notice_id,
                    )
                    continue

                if settings.scraper_search_term.upper() in title.upper():
                    logger.warning(
                        "Detected matching Upbit notice notice_id=%s listed_at=%s title=%s",
                        notice_id,
                        notice.get("listed_at"),
                        title,
                    )
                else:
                    logger.debug(
                        "Recorded non-matching Upbit notice notice_id=%s title=%s",
                        notice_id,
                        title,
                    )

                self.seen_notices.add(notice_id)

        except Exception:
            logger.exception("Failed to check Upbit trade notices")
