from datetime import datetime, timezone

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