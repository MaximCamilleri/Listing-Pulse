from decimal import Decimal
from typing import Any

from src.integration.binance_client import BinanceClient
from src.support.logger import get_logger


logger = get_logger(__name__)


class BinanceService:
    def __init__(self, binance_client: BinanceClient | None = None) -> None:
        self.binance_client = binance_client or BinanceClient()
        logger.debug("BinanceService initialized")

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
        # Validations 
        symbol = symbol.upper().strip()
        if not symbol:
            logger.error("Rejected market order with empty symbol")
            raise ValueError("symbol must not be empty.")

        quantity = Decimal(str(quantity))
        if quantity <= 0:
            logger.error(
                "Rejected market order with invalid quantity symbol=%s quantity=%s",
                symbol,
                quantity,
            )
            raise ValueError("quantity must be greater than zero.")

        callback_rate = Decimal(str(callback_rate))
        if not Decimal("0.1") <= callback_rate <= Decimal("10"):
            logger.error(
                "Rejected market order with invalid callback_rate symbol=%s callback_rate=%s",
                symbol,
                callback_rate,
            )
            raise ValueError("callback_rate must be between 0.1 and 10 percent.")

        direction = direction.upper().strip()
        if direction not in {"BUY", "SELL"}:
            logger.error(
                "Rejected market order with unsupported direction symbol=%s direction=%s",
                symbol,
                direction,
            )
            raise ValueError(
                f'Direction must be "BUY" or "SELL". "{direction}" is not supported.'
            )

        logger.info(
            "Placing Binance market entry order "
            "symbol=%s direction=%s quantity=%s callback_rate=%s",
            symbol,
            direction,
            quantity,
            callback_rate,
        )

        # Open trade
        entry = self.binance_client.place_market_order(
            symbol=symbol,
            side=direction,
            quantity=quantity,
        )

        executed_quantity = Decimal(str(entry.executed_qty))

        if executed_quantity <= 0:
            logger.error(
                "Binance entry order was not filled "
                "symbol=%s direction=%s status=%s order_id=%s executed_quantity=%s",
                symbol,
                direction,
                entry.status,
                entry.order_id,
                executed_quantity,
            )
            raise RuntimeError(f"Entry was not filled: {entry}")

        logger.info(
            "Binance market entry filled symbol=%s direction=%s executed_quantity=%s",
            symbol,
            direction,
            executed_quantity,
        )

        # Add trailing stop
        trailing_stop = self.binance_client.place_trailing_stop_order(
            symbol=symbol,
            side="SELL" if direction == "BUY" else "BUY",
            quantity=quantity,
            callback_rate=callback_rate,
        )

        logger.info(
            "Placed Binance trailing stop "
            "symbol=%s stop_side=%s quantity=%s callback_rate=%s",
            symbol,
            "SELL" if direction == "BUY" else "BUY",
            quantity,
            callback_rate,
        )

        return entry, trailing_stop
