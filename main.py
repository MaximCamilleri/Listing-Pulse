from src.service.scraper_service import ScraperService
from src.support.logger import configure_logging, get_logger


logger = get_logger(__name__)


def start_app():
    configure_logging()
    logger.info("Starting Upbit scraper application")
    scraper = ScraperService()
    try:
        scraper.start()
    except KeyboardInterrupt:
        logger.info("Upbit scraper application stopped by user")
    except Exception:
        logger.exception("Upbit scraper application stopped unexpectedly")
        raise


if __name__ == "__main__":
    start_app()
