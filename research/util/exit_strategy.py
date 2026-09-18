"""Tick-level trailing-stop trade simulation."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .binance_tick_feed import BinanceTickFeed, Tick
from .helper import normalize_symbol, timestamp_to_ms

DEFAULT_MAX_HOLD_MS = 24 * 60 * 60 * 1000

# ============================
#  Trailing Stop Exit
# ============================

def calculate_trailing_stop_pnl(
    ticks: Iterable[Tick], 
    trailing_stop_percent: float # 100 = 100%
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


# ============================
#  Volume Reduction Exit
# ============================

def calculate_volume_exit_pnl(
    ticks: Iterable[Tick],
    time_interval_ms: int, 
    volume_drop_percent: float # 100 = 100%
):  
    """Exit position once volume drops under 'volume_drop_percent' from the fist time interval"""
    if not 0 < volume_drop_percent < 100:
        raise ValueError("trailing_stop_percent must be greater than 0 and less than 100")

    iterator = iter(ticks)
    try:
        entry_tick = next(iterator)
    except StopIteration as exc:
        raise ValueError("no Binance trades found at or after the entry time") from exc

    entry_price = entry_tick.price
    entry_time = entry_tick.timestamp_ms
    if entry_price <= 0:
        raise ValueError("tick prices must be greater than zero")

    # 1. Accumulate benchmark_volume 
    benchmark_volume = entry_tick.quantity

    _tick = next(iterator)
    _next_check = entry_time + time_interval_ms
    while _tick.timestamp_ms < _next_check:
        benchmark_volume += _tick.quantity
        _tick = next(iterator)

    volume_threshold = benchmark_volume*(1-volume_drop_percent/100)
    # print(f"Benchmark Volume: {benchmark_volume}, Target Exit Volume: {volume_threshold}")

    # 2. Check for exit 
    _volume = 0
    _next_check += time_interval_ms
    for tick in iterator:
        if tick.timestamp_ms >= _next_check:
            if _volume <= volume_threshold: 
                return (tick.price / entry_price - 1) * 100
            _volume = 0

        _volume += tick.quantity

    raise RuntimeError("Exit was not triggered within the replay window")

def simulate_volume_exit(
    asset_name: str,
    entry_time: int | datetime,
    time_interval_ms: int, 
    volume_drop_percent: float,
    tick_feed: BinanceTickFeed | None = None,
    max_hold_ms: int = DEFAULT_MAX_HOLD_MS
) -> float:

    if max_hold_ms <= 0:
        raise ValueError("max_hold_ms must be greater than zero")

    start_time_ms = timestamp_to_ms(entry_time)
    feed = tick_feed or BinanceTickFeed()
    ticks = feed.iter_ticks(
        normalize_symbol(asset_name),
        start_time_ms,
        start_time_ms + max_hold_ms,
    )
    return calculate_volume_exit_pnl(ticks, time_interval_ms, volume_drop_percent)