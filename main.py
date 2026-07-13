import signal
import threading

from src.interface.notice_trading_workflow import create_notice_trade_handler
from src.service.scraper_service import ScraperService
from src.support.logger import configure_logging, get_logger


logger = get_logger(__name__)


def start_app(stop_event: threading.Event | None = None) -> None:
    configure_logging()
    logger.info("Starting Upbit scraper application")

    stop_event = stop_event or threading.Event()
    _configure_shutdown_signals(stop_event)

    scraper = ScraperService(
        on_new_notice=create_notice_trade_handler(),
        stop_event=stop_event,
    )
    try:
        scraper.start()
    except KeyboardInterrupt:
        stop_event.set()
        logger.info("Upbit scraper application stopped by user")
    except Exception:
        logger.exception("Upbit scraper application stopped unexpectedly")
        raise


def _configure_shutdown_signals(stop_event: threading.Event) -> None:
    def request_shutdown(signum, _frame) -> None:
        logger.info("Shutdown signal received signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)


if __name__ == "__main__":
    start_app()
