from typing import Any

from curl_cffi import requests

from src.config.settings import settings


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
            "search": search_term,
            "page": 1,
            "per_page": 20,
            "_t": timestamp_ms,
        }

        response = requests.get(
            settings.scraper_url,
            headers=HEADERS,
            params=params,
            impersonate="chrome",
            timeout=settings.scraper_timeout,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Upbit notices request failed with status {response.status_code}"
            )

        data = response.json()
        return data.get("data", {}).get("notices", [])
