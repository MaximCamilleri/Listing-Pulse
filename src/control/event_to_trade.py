"""Compose an event source and trading destination without starting either."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

from src.config.settings import settings
from src.control.trade.binance_controller import BinanceController
from src.control.event.listener_factory import EVENT_CHANNELS, listener_factory
from src.control.event.message_parser import parse_bithumb_telegram_notice, parse_upbit_telegram_notice
from src.control.event.telegram_controller import MessageHandler, TelegramMessage
from src.support.latency_profiler import LatencyProfiler
from src.support.logger import get_logger
from src.integration.telegram_integration import TelegramIntegration

TRADE_CHANNELS = Literal["BINANCE"]
logger = get_logger(__name__)


class EventToTrade:
    def __init__(
        self,
        event_source: EVENT_CHANNELS,
        trade_source: TRADE_CHANNELS,
        *,
        trade_control: BinanceController | None = None,
        message_handler: MessageHandler | None = None,
        telegram: TelegramIntegration | None = None,
    ) -> None:
        parsers = {
            "UPBIT": parse_upbit_telegram_notice,
            "BITHUMB": parse_bithumb_telegram_notice,
        }
        if event_source not in parsers:
            raise ValueError(f"Unsupported event source: {event_source}")
        if trade_source != "BINANCE":
            raise ValueError(f"Unsupported trade source: {trade_source}")

        self.event_source = event_source
        self.trade_source = trade_source
        self.parse_function = parsers[event_source]
        self.trade_control = trade_control if trade_control is not None else BinanceController(
            margin_amount=settings.order_margin_amount
        )
        self.event_control = listener_factory(
            event_source,
            message_handler if message_handler is not None else self.trigger_action,
            telegram=telegram,
        )

    async def trigger_action(
        self,
        message: TelegramMessage,
        latency_profiler: LatencyProfiler | None = None,
    ) -> None:
        await _trigger_action(
            message, self.trade_control, self.parse_function, latency_profiler
        )


async def _place_order_and_log_latency(
    *,
    message: TelegramMessage,
    pair: str,
    trade_control: BinanceController,
    latency_profiler: LatencyProfiler | None = None,
) -> None:
    kwargs = {
        "symbol": pair,
        "direction": settings.order_direction,
        "callback_rate": settings.order_callback_rate,
    }
    if latency_profiler is not None:
        kwargs["latency_profiler"] = latency_profiler
    result = await trade_control.place_market_order(**kwargs)
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
    parse_function: Callable[[TelegramMessage], list[str]] | None = None,
    latency_profiler: LatencyProfiler | None = None,
) -> None:
    parse_function = parse_function or parse_upbit_telegram_notice
    logger.info("Received Telegram message channel_id=%s message_id=%s", message.channel_id, message.message_id)
    if latency_profiler is None:
        target_assets = parse_function(message)
    else:
        with latency_profiler.span("notice.parse_and_filter"):
            target_assets = parse_function(message)

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
                latency_profiler=latency_profiler,
            )
        )

    await asyncio.gather(*order_tasks)

