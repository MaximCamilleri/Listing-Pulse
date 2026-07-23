from src.control.telegram_controller import TelegramController, TelegramMessage
from src.control.binance_controller import BinanceController
from src.control.message_parser import parse_upbit_telegram_notice
from src.support.logger import get_logger
from src.config.settings import settings
import asyncio
import threading
from datetime import datetime, timezone

logger = get_logger(__name__)


async def _place_order_and_log_latency(
    *,
    message: TelegramMessage,
    pair: str,
    trade_control: BinanceController,
) -> None:
    result = await trade_control.place_market_order(
        symbol=pair,
        quote_amount=settings.order_quote_amount,
        direction=settings.order_direction,
        callback_rate=settings.order_callback_rate,
    )
    if result is None:
        return

    entry, _ = result
    order_opened_at = datetime.fromtimestamp(
        entry.update_time / 1_000,
        tz=timezone.utc,
    )
    notice_placed_at = message.date
    if notice_placed_at.tzinfo is None:
        notice_placed_at = notice_placed_at.replace(tzinfo=timezone.utc)

    latency_seconds = (order_opened_at - notice_placed_at).total_seconds()
    logger.info(
        "Opened order from Telegram notice "
        "symbol=%s channel_id=%s message_id=%s latency_seconds=%.3f "
        "notice_placed_at=%s order_opened_at=%s",
        pair,
        message.channel_id,
        message.message_id,
        latency_seconds,
        notice_placed_at.isoformat(),
        order_opened_at.isoformat(),
    )


async def _trigger_action(
    message: TelegramMessage,
    trade_control: BinanceController,
) -> None:
    logger.info("Received new telegram message")
    target_assets = parse_upbit_telegram_notice(message)

    if not target_assets:
        logger.info("Skipping notice: No new KRW listings")
        return

    # Preserve notice order while preventing duplicate orders for one asset.
    target_assets = list(dict.fromkeys(target_assets))
    logger.info("New KRW listing for: %s", target_assets)

    order_tasks = []
    for asset in target_assets:
        pair = asset + settings.order_quote_asset
        logger.info("Placing trade on: %s", pair)

        order_tasks.append(
            _place_order_and_log_latency(
                message=message,
                pair=pair,
                trade_control=trade_control,
            )
        )

    await asyncio.gather(*order_tasks)


async def start_trader(stop_event: threading.Event | None = None):
    stop_event = stop_event or threading.Event()

    # Trade Setup
    trade_control = BinanceController()

    async def trigger_action(message: TelegramMessage) -> None:
        await _trigger_action(message, trade_control)

    # Listener Setup
    telegram_kwargs = {
        "session_string" : settings.telegram_session,
        "api_id" : settings.telegram_api_id,
        "api_hash" : settings.telegram_api_hash,
        "phone" : settings.telegram_phone,
        "telegram_connection_retries" : settings.telegram_connection_retries,
        "telegram_retry_delay" : settings.telegram_retry_delay,
        "supervisor_initial_delay" : settings.telegram_supervisor_initial_delay,
        "supervisor_max_delay" : settings.telegram_supervisor_max_delay,
        "healthcheck_interval_seconds" : settings.healthcheck_interval_seconds,
    }

    trigger_control = TelegramController(
        telegram_kwargs = telegram_kwargs, 
        channel = settings.telegram_channel,
        message_handler = trigger_action
    )

    controller_task = asyncio.create_task(
        trigger_control.run(),
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
            await trigger_control.stop()

        await controller_task

    except Exception:
        logger.exception("Upbit scraper application stopped unexpectedly")
        raise

    finally:
        stop_event.set()
        shutdown_task.cancel()
        await trigger_control.stop()


async def _wait_for_shutdown(stop_event: threading.Event) -> None:
    """Bridge the process-safe shutdown flag into the asyncio lifecycle."""
    while not stop_event.is_set():
        await asyncio.sleep(0.1)
