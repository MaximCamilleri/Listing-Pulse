import asyncio
import signal
import threading

from src.interface.trade_interface import start_trader
from src.support.logger import configure_logging, get_logger
from src.support.healthcheck import reset_health

logger = get_logger(__name__)


def _configure_shutdown_signals(stop_event: threading.Event) -> None:
    def request_shutdown(signum, _frame) -> None:
        logger.info("Shutdown signal received signal=%s", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

if __name__ == "__main__":
    configure_logging()
    reset_health()
    shutdown_event = threading.Event()
    _configure_shutdown_signals(shutdown_event)
    asyncio.run(start_trader(stop_event=shutdown_event))
