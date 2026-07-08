from src.config.settings import settings
from curl_cffi import requests

import time 
import random
import logging 

# logger = logging.get

HEADERS = {
    "Accept" : "application/json",
    "Referer" : "https://upbit.com",
    "Accept-Language" : "en-US,en;q=0.9,ko;q=0.9"
}

class ScraperService():
    def __init__(self):
        self.seen_notices = set()

    def start(self):
        while True:
            self.check_for_notice()

            sleep_time = random.uniform(
                settings.scraper_cooldown - settings.scraper_cooldown_offset,
                settings.scraper_cooldown + settings.scraper_cooldown_offset
            )
            time.sleep(sleep_time)

    def check_for_notice(self):
        try:
            params = {
                "os" : "web",
                "category" : "trade",
                "search" : settings.scraper_search_term,
                "page" : 1,
                "per_page" : 20,
                "_t" : int(time.time() * 1000),
            }

            response = requests.get(
                settings.scraper_url,
                headers = HEADERS, 
                params = params, 
                impersonate = "chrome", 
                timeout = settings.scraper_timeout
            )

            if response.status_code != 200:
                print()
                return 
            
            data = response.json()
            notices = data.get("data", {}).get("notices", [])
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
