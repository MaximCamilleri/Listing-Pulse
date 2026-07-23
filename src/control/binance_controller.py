from decimal import Decimal, ROUND_DOWN

from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    NewAlgoOrderResponse,
    NewOrderResponse,
)

from src.integration.binance_integration import BinanceIntegration
from src.config.settings import settings
from src.support.logger import get_logger


logger = get_logger(__name__)


class BinanceController:
    def __init__(self, binance_client: BinanceIntegration | None = None) -> None:
        self.binance_client = binance_client or BinanceIntegration()
        logger.debug("BinanceService initialized")

    async def place_market_order(
        self,
        symbol: str,
        quote_amount: Decimal,
        direction: str,
        callback_rate: Decimal,
    ) -> tuple[NewOrderResponse, NewAlgoOrderResponse]:
        """
        Open a position and place a trailing stop beneath it.

        direction:
            "BUY" for long
            "SELL" for short

        callback_rate:
            Percentage retracement, e.g. Decimal("1.0") means 1%.

        """
        # Validations 
        if settings.trading_enabled == False: 
            logger.error(
                "Failed to place trade on symbol=%s because trading is disabled",
                symbol
            )
            return 

        symbol = symbol.upper().strip()
        if not symbol:
            logger.error("Rejected market order with empty symbol")
            raise ValueError("symbol must not be empty.")

        quote_amount = Decimal(str(quote_amount))
        if quote_amount <= 0:
            logger.error(
                "Rejected market order with invalid quote amount "
                "symbol=%s quote_amount=%s",
                symbol,
                quote_amount,
            )
            raise ValueError("quote_amount must be greater than zero.")

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

        market_rules = await self.binance_client.get_market_rules(symbol)
        if market_rules.status != "TRADING":
            raise ValueError(
                f"Binance futures symbol is not trading: {symbol} "
                f"(status={market_rules.status})"
            )

        price = await self.binance_client.get_symbol_price(symbol)
        if price <= 0:
            raise RuntimeError(f"Binance returned an invalid price for {symbol}: {price}")

        quantity = (
            (quote_amount / price / market_rules.step_size).to_integral_value(
                rounding=ROUND_DOWN
            )
            * market_rules.step_size
        )
        if quantity < market_rules.min_quantity:
            raise ValueError(
                f"quote_amount produces quantity below the market minimum for {symbol}: "
                f"quote_amount={quote_amount} price={price} "
                f"quantity={quantity} min_quantity={market_rules.min_quantity}"
            )
        if quantity > market_rules.max_quantity:
            raise ValueError(
                f"quote_amount produces quantity above the market maximum for {symbol}: "
                f"quantity={quantity} max_quantity={market_rules.max_quantity}"
            )

        estimated_notional = quantity * price
        if estimated_notional < market_rules.min_notional:
            raise ValueError(
                f"quote_amount is below Binance's minimum notional for {symbol}: "
                f"estimated_notional={estimated_notional} "
                f"min_notional={market_rules.min_notional}"
            )

        leverage_brackets = await self.binance_client.get_leverage_brackets(symbol)
        matching_bracket = next(
            (
                bracket
                for bracket in sorted(
                    leverage_brackets,
                    key=lambda item: item.notional_floor,
                )
                if (
                    bracket.notional_floor
                    <= estimated_notional
                    < bracket.notional_cap
                )
            ),
            None,
        )
        if matching_bracket is None:
            raise ValueError(
                f"No Binance leverage bracket supports notional "
                f"{estimated_notional} for {symbol}"
            )

        leverage = matching_bracket.initial_leverage
        await self.binance_client.set_initial_leverage(symbol, leverage)

        logger.info(
            "Placing Binance market entry order "
            "symbol=%s direction=%s quote_amount=%s price=%s quantity=%s "
            "estimated_notional=%s leverage=%s callback_rate=%s",
            symbol,
            direction,
            quote_amount,
            price,
            quantity,
            estimated_notional,
            leverage,
            callback_rate,
        )

        # Open trade
        entry = await self.binance_client.place_market_order(
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
        trailing_stop = await self.binance_client.place_trailing_stop_order(
            symbol=symbol,
            side="SELL" if direction == "BUY" else "BUY",
            quantity=executed_quantity,
            callback_rate=callback_rate,
        )

        logger.info(
            "Placed Binance trailing stop "
            "symbol=%s stop_side=%s quantity=%s callback_rate=%s",
            symbol,
            "SELL" if direction == "BUY" else "BUY",
            executed_quantity,
            callback_rate,
        )

        return entry, trailing_stop
