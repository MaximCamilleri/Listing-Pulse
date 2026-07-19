"""Tick-level trailing-stop trade simulation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from .binance_tick_feed import BinanceTickFeed, Tick


DEFAULT_QUOTE_ASSET = "USDT"
DEFAULT_MAX_HOLD_MS = 24 * 60 * 60 * 1000


def normalize_symbol(asset_name: str) -> str:
    """Convert an asset such as ``BTC`` or ``BTCUSDT`` to a Futures symbol."""
    symbol = asset_name.upper().strip()
    if not symbol:
        raise ValueError("asset_name must not be empty")
    return symbol if symbol.endswith(DEFAULT_QUOTE_ASSET) else f"{symbol}USDT"


def timestamp_to_ms(entry_time: int | datetime) -> int:
    """Return a UTC Unix timestamp in milliseconds."""
    if isinstance(entry_time, bool):
        raise TypeError("entry_time must be an integer timestamp or datetime")
    if isinstance(entry_time, int):
        if entry_time < 0:
            raise ValueError("entry_time must be non-negative")
        return entry_time
    if isinstance(entry_time, datetime):
        if entry_time.tzinfo is None:
            raise ValueError("datetime entry_time must be timezone-aware")
        return int(entry_time.astimezone(timezone.utc).timestamp() * 1000)
    raise TypeError("entry_time must be an integer timestamp or datetime")


def calculate_trailing_stop_pnl(
    ticks: Iterable[Tick], trailing_stop_percent: float
) -> float:
    """Calculate long-trade percentage PnL from chronologically ordered ticks."""
    rate = float(trailing_stop_percent)
    if not 0 < rate < 100:
        raise ValueError("trailing_stop_percent must be greater than 0 and less than 100")

    iterator = iter(ticks)
    try:
        entry_tick = next(iterator)
    except StopIteration as exc:
        raise ValueError("no Binance trades found at or after the entry time") from exc

    entry_price = entry_tick.price
    if entry_price <= 0:
        raise ValueError("tick prices must be greater than zero")

    high_watermark = entry_price
    multiplier = 1 - rate / 100
    for tick in iterator:
        if tick.price <= 0:
            raise ValueError("tick prices must be greater than zero")
        high_watermark = max(high_watermark, tick.price)
        if tick.price <= high_watermark * multiplier:
            return (tick.price / entry_price - 1) * 100

    raise RuntimeError("trailing stop was not triggered within the replay window")


def simulate_trailing_stop(
    asset_name: str,
    entry_time: int | datetime,
    trailing_stop_percent: float,
    *,
    tick_feed: BinanceTickFeed | None = None,
    max_hold_ms: int = DEFAULT_MAX_HOLD_MS,
) -> float:
    """Replay a long trailing stop and return percentage PnL before costs.

    Entry fills at the first aggregate trade at or after ``entry_time``. The
    stop activates immediately, follows the highest subsequent trade price,
    and fills at the first observed trade at or below the stop threshold.
    Old data is downloaded from Binance's daily public archive and cached in
    ``research/data/binance``; recent data is read from the Futures REST API.
    """
    if max_hold_ms <= 0:
        raise ValueError("max_hold_ms must be greater than zero")

    start_time_ms = timestamp_to_ms(entry_time)
    feed = tick_feed or BinanceTickFeed()
    ticks = feed.iter_ticks(
        normalize_symbol(asset_name),
        start_time_ms,
        start_time_ms + max_hold_ms,
    )
    return calculate_trailing_stop_pnl(ticks, trailing_stop_percent)

