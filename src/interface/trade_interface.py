from src.control.telegram_controller import TelegramController
from src.support.logger import get_logger
from src.config.settings import settings
import asyncio
import threading

logger = get_logger(__name__)

async def start_trader(stop_event: threading.Event | None = None):
    stop_event = stop_event or threading.Event()

    telegram_kwargs = {
        "api_id" : settings.telegram_api_id,
        "api_hash" : settings.telegram_api_hash,
        "session_name" : "telegram_listener",
        "phone" : settings.telegram_phone,
        "telegram_connection_retries" : settings.telegram_connection_retries,
        "telegram_retry_delay" : settings.telegram_retry_delay,
        "supervisor_initial_delay" : settings.telegram_supervisor_initial_delay,
        "supervisor_max_delay" : settings.telegram_supervisor_max_delay,
    }

    controller = TelegramController(
        telegram_kwargs = telegram_kwargs, 
        channel = settings.telegram_channel
    )

    controller_task = asyncio.create_task(
        controller.run(),
        name="telegram-controller",
    )
    shutdown_task = asyncio.create_task(
        _wait_for_shutdown(stop_event),
        name="shutdown-waiter",
    )

    try:
        done, _ = await asyncio.wait(
            (controller_task, shutdown_task),
            return_when=asyncio.FIRST_COMPLETED,
        )

        if shutdown_task in done:
            logger.info("Application shutdown requested")
            await controller.stop()

        await controller_task

    except Exception:
        logger.exception("Upbit scraper application stopped unexpectedly")
        raise

    finally:
        stop_event.set()
        shutdown_task.cancel()
        await controller.stop()


async def _wait_for_shutdown(stop_event: threading.Event) -> None:
    """Bridge the process-safe shutdown flag into the asyncio lifecycle."""
    while not stop_event.is_set():
        await asyncio.sleep(0.1)
