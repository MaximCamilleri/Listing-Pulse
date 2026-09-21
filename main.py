import asyncio
import signal
import threading

from src.config.settings import settings
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

    combinations = []
    if settings.upbit_telegram_channel.strip():
        combinations.append(("UPBIT", "BINANCE"))
    if settings.bithumb_telegram_channel.strip():
        combinations.append(("BITHUMB", "BINANCE"))

    if not combinations:
        logger.error("Set UPBIT_TELEGRAM_CHANNEL or BITHUMB_TELEGRAM_CHANNEL to start a listener")
        raise SystemExit(1)

    logger.info("Starting event/trade workflows: %s", combinations)
    shutdown_event = threading.Event()
    _configure_shutdown_signals(shutdown_event)
    asyncio.run(start_trader(stop_event=shutdown_event, combinations=combinations))
