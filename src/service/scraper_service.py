import random
import threading
import time
from collections.abc import Callable
from typing import Any

from src.config.settings import settings
from src.integration.upbit_client import UpbitClient
from src.support.logger import get_logger


logger = get_logger(__name__)

NoticeHandler = Callable[[dict[str, Any]], None]


class ScraperService:
    def __init__(
        self,
        upbit_client: UpbitClient | None = None,
        on_new_notice: NoticeHandler | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self.upbit_client = upbit_client or UpbitClient()
        self.on_new_notice = on_new_notice
        self.stop_event = stop_event or threading.Event()
        self.seen_notices: set[Any] = set()
        logger.debug("ScraperService initialized")

    def start(self) -> None:
        logger.info(
            "Starting scraper loop search_term=%s cooldown_seconds=%.2f offset_seconds=%.2f",
            settings.scraper_search_term,
            settings.scraper_cooldown,
            settings.scraper_cooldown_offset,
        )
        while not self.stop_event.is_set() and not self.initialize_seen_notices():
            sleep_time = random.uniform(
                settings.scraper_cooldown - settings.scraper_cooldown_offset,
                settings.scraper_cooldown + settings.scraper_cooldown_offset,
            )
            self._sleep(sleep_time)

        while not self.stop_event.is_set():
            self.check_for_notice()

            sleep_time = random.uniform(
                settings.scraper_cooldown - settings.scraper_cooldown_offset,
                settings.scraper_cooldown + settings.scraper_cooldown_offset,
            )
            self._sleep(sleep_time)

        logger.info("Scraper loop stopped")

    def initialize_seen_notices(self) -> bool:
        try:
            checked_at = time.time()
            notices = self.upbit_client.fetch_trade_notices(
                search_term=settings.scraper_search_term,
                timestamp_ms=int(checked_at * 1000),
            )

            for notice in notices:
                notice_id = notice.get("id")
                if notice_id is None:
                    logger.warning(
                        "Skipping Upbit notice without id during baseline title=%s",
                        notice.get("title", ""),
                    )
                    continue

                self.seen_notices.add(notice_id)

            logger.info(
                "Initialized Upbit notice baseline result_count=%d seen_notice_count=%d",
                len(notices),
                len(self.seen_notices),
            )
            return True

        except Exception:
            logger.exception("Failed to initialize Upbit notice baseline")
            return False

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

                if notice_id is None:
                    logger.warning(
                        "Skipping Upbit notice without id title=%s",
                        title,
                    )
                    continue

                if notice_id in self.seen_notices:
                    logger.debug(
                        "Skipping previously seen notice notice_id=%s",
                        notice_id,
                    )
                    continue

                logger.info(
                    "Recorded new Upbit notice notice_id=%s title=%s",
                    notice_id,
                    title,
                )

                self.seen_notices.add(notice_id)
                if self.on_new_notice is not None:
                    self.on_new_notice(notice)

        except Exception:
            logger.exception("Failed to check Upbit trade notices")

    def _sleep(self, sleep_time: float) -> None:
        self.stop_event.wait(max(0.0, sleep_time))
