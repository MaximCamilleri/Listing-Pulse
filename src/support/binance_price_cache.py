from dataclasses import dataclass
from decimal import Decimal
import time
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class BinanceLivePrice:
    symbol: str
    price: Decimal
    exchange_time_ms: int | None
    received_at: float


class BinancePriceCache:
    """Event-loop-owned cache of bounded-age Binance futures prices."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._prices: dict[str, BinanceLivePrice] = {}

    def update_message(self, message: Any) -> None:
        items = message if isinstance(message, list) else [message]
        received_at = self._clock()
        for item in items:
            symbol = self._field(item, "s")
            price = self._field(item, "c")
            if not symbol or price is None:
                continue
            parsed_price = Decimal(str(price))
            if parsed_price <= 0:
                continue
            self._prices[str(symbol).upper()] = BinanceLivePrice(
                symbol=str(symbol).upper(),
                price=parsed_price,
                exchange_time_ms=self._field(item, "E"),
                received_at=received_at,
            )

    def require(self, symbol: str, max_age_seconds: float) -> BinanceLivePrice:
        value = self._prices.get(symbol)
        if value is None:
            raise RuntimeError(f"No live Binance price is available for {symbol}")
        age = self._clock() - value.received_at
        if age > max_age_seconds:
            raise RuntimeError(
                f"Live Binance price is stale for {symbol}: age_seconds={age:.3f}"
            )
        return value

    @staticmethod
    def _field(item: Any, name: str) -> Any:
        if isinstance(item, dict):
            return item.get(name)
        return getattr(item, name, None)
