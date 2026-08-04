from datetime import datetime, timezone

from .binance_tick_feed import BinanceTickFeed

DEFAULT_QUOTE_ASSET = "USDT"

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


def calculate_max_pnl(
    asset_name: str,
    start_time: int | datetime,
    end_time: int | datetime,
    *,
    tick_feed: BinanceTickFeed | None = None,
) -> float:
    """Return the maximum percentage PnL observed during an inclusive time range.

    Entry is assumed to fill at the first aggregate trade at or after
    ``start_time``. The result is the greatest unrealized long-position PnL
    available from that entry through ``end_time``, before fees and slippage.
    """
    start_time_ms = timestamp_to_ms(start_time)
    end_time_ms = timestamp_to_ms(end_time)
    if end_time_ms < start_time_ms:
        raise ValueError("end_time must not be earlier than start_time")

    feed = tick_feed or BinanceTickFeed()
    iterator = iter(
        feed.iter_ticks(
            normalize_symbol(asset_name),
            start_time_ms,
            end_time_ms,
        )
    )

    try:
        entry_tick = next(iterator)
    except StopIteration as exc:
        raise ValueError("no Binance trades found in the requested time range") from exc

    entry_price = entry_tick.price
    if entry_price <= 0:
        raise ValueError("tick prices must be greater than zero")

    maximum_price = entry_price
    for tick in iterator:
        if tick.price <= 0:
            raise ValueError("tick prices must be greater than zero")
        maximum_price = max(maximum_price, tick.price)

    return (maximum_price / entry_price - 1) * 100
