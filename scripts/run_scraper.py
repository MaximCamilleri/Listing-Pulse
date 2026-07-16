import signal
import sys
import threading
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.control.scraper_service import ScraperService
from src.support.logger import configure_logging, get_logger


logger = get_logger(__name__)


def run_scraper(stop_event: threading.Event | None = None) -> None:
    """Run the scraper without installing a handler for newly detected notices."""
    configure_logging()
    logger.info("Starting observation-only Upbit scraper")

    stop_event = stop_event or threading.Event()
    _configure_shutdown_signals(stop_event)
    scraper = ScraperService(stop_event=stop_event)

    try:
        scraper.start()
    except KeyboardInterrupt:
        stop_event.set()
        logger.info("Observation-only Upbit scraper stopped by user")
    except Exception:
        logger.exception("Observation-only Upbit scraper stopped unexpectedly")
        raise


def _configure_shutdown_signals(stop_event: threading.Event) -> None:
    def request_shutdown(signum, _frame) -> None:
        logger.info("Shutdown signal received signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


if __name__ == "__main__":
    run_scraper()
