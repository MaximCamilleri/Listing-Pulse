from typing import Any

from curl_cffi import requests

from src.config.settings import settings
from src.support.logger import get_logger


logger = get_logger(__name__)


HEADERS = {
    "Accept": "application/json",
    "Referer": "https://upbit.com",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.9",
}


class UpbitClient:
    def fetch_trade_notices(
        self,
        search_term: str,
        timestamp_ms: int,
    ) -> list[dict[str, Any]]:
        params = {
            "os": "web",
            "category": "trade",
            "page": 1,
            "per_page": 20,
            "_t": timestamp_ms,
        }
        normalized_search_term = search_term.strip()
        if normalized_search_term:
            params["search"] = normalized_search_term

        logger.debug(
            "Requesting Upbit trade notices url=%s search_term=%s timeout_seconds=%.2f",
            settings.scraper_url,
            normalized_search_term or "<all>",
            settings.scraper_timeout,
        )
        response = requests.get(
            settings.scraper_url,
            headers=HEADERS,
            params=params,
            impersonate="chrome",
            timeout=settings.scraper_timeout,
        )

        if response.status_code != 200:
            logger.error(
                "Upbit notices request failed status_code=%s response_text=%s",
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError(
                f"Upbit notices request failed with status {response.status_code}"
            )

        data = response.json()
        notices = data.get("data", {}).get("notices", [])
        logger.debug("Upbit notices request succeeded result_count=%d", len(notices))
        return notices
