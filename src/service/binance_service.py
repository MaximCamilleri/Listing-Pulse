from decimal import Decimal
from typing import Any

from src.integration.binance_client import BinanceClient


class BinanceService:
    def __init__(self, binance_client: BinanceClient | None = None) -> None:
        self.binance_client = binance_client or BinanceClient()

    def place_market_order(
        self,
        symbol: str,
        quantity: Decimal,
        direction: str,
        callback_rate: Decimal,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """
        Open a position and place a trailing stop beneath it.

        direction:
            "BUY" for long 
            "SELL" for short 

        callback_rate:
            Percentage retracement, e.g. Decimal("1.0") means 1%.

        """
        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("symbol must not be empty.")

        quantity = Decimal(str(quantity))
        if quantity <= 0:
            raise ValueError("quantity must be greater than zero.")

        callback_rate = Decimal(str(callback_rate))
        if not Decimal("0.1") <= callback_rate <= Decimal("10"):
            raise ValueError("callback_rate must be between 0.1 and 10 percent.")

        direction = direction.upper().strip()
        if direction not in {"BUY", "SELL"}:
            raise ValueError(
                f'Direction must be "BUY" or "SELL". "{direction}" is not supported.'
            )

        entry = self.binance_client.place_market_order(
            symbol=symbol,
            side=direction,
            quantity=quantity,
        )

        executed_quantity = Decimal(str(entry.get("executedQty", "0")))

        if executed_quantity <= 0:
            raise RuntimeError(f"Entry was not filled: {entry}")

        trailing_stop = self.binance_client.place_trailing_stop_order(
            symbol=symbol,
            side="SELL" if direction == "BUY" else "BUY",
            quantity=quantity,
            callback_rate=callback_rate,
        )

        return entry, trailing_stop
