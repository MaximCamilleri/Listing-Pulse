"""Run the production signal-to-trade path with per-notice latency allocation.

This diagnostic intentionally supports Binance DEMO only. It listens to the
configured Telegram channel and exercises real testnet requests.
"""

import asyncio
import signal
import threading
from datetime import datetime, timezone

from main import _configure_shutdown_signals
from src.config.settings import settings
from src.control.binance_controller import BinanceController
from src.interface.trade_interface import _trigger_action, start_trader
from src.support.healthcheck import reset_health
from src.support.latency_profiler import LatencyProfiler
from src.support.logger import configure_logging, get_logger

logger = get_logger(__name__)


async def main(stop_event: threading.Event) -> None:
    if settings.trade_environment != "DEMO":
        raise RuntimeError("Latency exercise is restricted to trade_environment=DEMO")
    if not settings.trading_enabled:
        raise RuntimeError("Set TRADING_ENABLED=true to exercise DEMO order placement")

    trade_control = BinanceController()

    async def profiled_trigger(message) -> None:
        profiler = LatencyProfiler()
        received_at = datetime.now(timezone.utc)
        notice_at = message.date
        if notice_at.tzinfo is None:
            notice_at = notice_at.replace(tzinfo=timezone.utc)
        dispatch_age = (received_at - notice_at).total_seconds()

        try:
            await _trigger_action(
                message,
                trade_control,
                latency_profiler=profiler,
            )
        finally:
            total = profiler.elapsed_seconds
            logger.info(
                "LATENCY REPORT channel_id=%s message_id=%s "
                "notice_to_handler_seconds=%.6f trigger_wall_seconds=%.6f",
                message.channel_id,
                message.message_id,
                dispatch_age,
                total,
            )
            for span in sorted(
                profiler.spans,
                key=lambda item: item.duration_seconds,
                reverse=True,
            ):
                logger.info(
                    "LATENCY ALLOCATION action=%s seconds=%.6f "
                    "trigger_wall_percent=%.1f task=%s",
                    span.name,
                    span.duration_seconds,
                    (span.duration_seconds / total * 100) if total else 0,
                    span.task_name,
                )

    await start_trader(
        stop_event=stop_event,
        trade_control=trade_control,
        message_handler=profiled_trigger,
    )


if __name__ == "__main__":
    configure_logging()
    reset_health()
    shutdown_event = threading.Event()
    _configure_shutdown_signals(shutdown_event)
    asyncio.run(main(shutdown_event))
