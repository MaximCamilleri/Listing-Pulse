from src.service.scraper_service import ScraperService

def start_app():
    scraper = ScraperService()
    scraper.start()

if __name__ == "__main__":
    start_app()