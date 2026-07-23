import asyncio
from dataclasses import dataclass
from decimal import Decimal

from binance_common.configuration import ConfigurationRestAPI
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
)
from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    NewAlgoOrderResponse,
    NewOrderResponse,
)

from src.config.settings import settings
from src.support.logger import get_logger
logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BinanceMarketRules:
    symbol: str
    status: str
    step_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal


@dataclass(frozen=True, slots=True)
class BinanceLeverageBracket:
    notional_floor: Decimal
    notional_cap: Decimal
    initial_leverage: int


class BinanceIntegration:
    def __init__(self) -> None:
        config = {
            "api_key": settings.binance_api_key,
            "api_secret": settings.binance_api_secret,
        }
        if settings.trade_environment == "DEMO":
            config["base_path"] = "https://testnet.binancefuture.com"

        self.client = DerivativesTradingUsdsFutures(
            config_rest_api=ConfigurationRestAPI(**config)
        )
        logger.info(
            "Initialized Binance futures client trade_environment=%s testnet=%s",
            settings.trade_environment,
            settings.trade_environment == "DEMO",
        )

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
    ) -> NewOrderResponse:
        """Place a market order without blocking the caller's event loop."""
        logger.info(
            "Submitting Binance market order symbol=%s side=%s quantity=%s",
            symbol,
            side,
            quantity,
        )
        try:
            response = await asyncio.to_thread(
                self._place_market_order_sync,
                symbol,
                side,
                quantity,
            )
        except Exception:
            logger.exception(
                "Binance market order request failed symbol=%s side=%s quantity=%s",
                symbol,
                side,
                quantity,
            )
            raise

        logger.info(
            "Binance market order accepted symbol=%s side=%s status=%s order_id=%s",
            symbol,
            side,
            response.status,
            response.order_id,
        )
        return response

    def _place_market_order_sync(self,
        symbol: str,
        side: str,
        quantity: Decimal,
    ) -> NewOrderResponse:
        return self.client.rest_api.new_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=float(quantity),
            reduce_only=False,
            new_order_resp_type="RESULT",
        ).data()

    async def get_market_rules(self, symbol: str) -> BinanceMarketRules:
        """Return the market-order sizing rules for one futures symbol."""
        response = await asyncio.to_thread(
            self.client.rest_api.exchange_information
        )
        exchange_info = response.data()
        symbol_info = next(
            (
                item
                for item in exchange_info.symbols or []
                if item.symbol == symbol
            ),
            None,
        )
        if symbol_info is None:
            raise ValueError(f"Binance futures symbol is unavailable: {symbol}")

        filters = {
            item.filter_type: item
            for item in symbol_info.filters or []
            if item.filter_type
        }
        lot_size = filters.get("MARKET_LOT_SIZE")
        min_notional = filters.get("MIN_NOTIONAL")
        if lot_size is None or min_notional is None:
            raise RuntimeError(
                f"Binance market sizing rules are incomplete for {symbol}"
            )

        return BinanceMarketRules(
            symbol=symbol_info.symbol,
            status=symbol_info.status,
            step_size=Decimal(lot_size.step_size),
            min_quantity=Decimal(lot_size.min_qty),
            max_quantity=Decimal(lot_size.max_qty),
            min_notional=Decimal(min_notional.notional),
        )

    async def get_symbol_price(self, symbol: str) -> Decimal:
        """Return Binance's latest futures price for one symbol."""
        response = await asyncio.to_thread(
            self.client.rest_api.symbol_price_ticker_v2,
            symbol,
        )
        ticker = response.data().actual_instance
        if ticker is None or isinstance(ticker, list) or ticker.price is None:
            raise RuntimeError(f"Binance returned no price for {symbol}")
        return Decimal(ticker.price)

    async def get_leverage_brackets(
        self,
        symbol: str,
    ) -> list[BinanceLeverageBracket]:
        """Return the account-specific notional and leverage brackets."""
        response = await asyncio.to_thread(
            self.client.rest_api.notional_and_leverage_brackets,
            symbol,
        )
        bracket_response = response.data().actual_instance
        if bracket_response is None or isinstance(bracket_response, list):
            raise RuntimeError(f"Binance returned no leverage brackets for {symbol}")

        return [
            BinanceLeverageBracket(
                notional_floor=Decimal(str(bracket.notional_floor)),
                notional_cap=Decimal(str(bracket.notional_cap)),
                initial_leverage=bracket.initial_leverage,
            )
            for bracket in bracket_response.brackets or []
        ]

    async def set_initial_leverage(self, symbol: str, leverage: int) -> None:
        """Set the account's initial leverage for one futures symbol."""
        logger.info(
            "Setting Binance initial leverage symbol=%s leverage=%s",
            symbol,
            leverage,
        )
        try:
            response = await asyncio.to_thread(
                self.client.rest_api.change_initial_leverage,
                symbol,
                leverage,
            )
            result = response.data()
        except Exception:
            logger.exception(
                "Failed to set Binance initial leverage symbol=%s leverage=%s",
                symbol,
                leverage,
            )
            raise

        if result.leverage != leverage:
            raise RuntimeError(
                f"Binance set leverage to {result.leverage}, expected {leverage}"
            )
        logger.info(
            "Set Binance initial leverage symbol=%s leverage=%s",
            symbol,
            leverage,
        )

    async def place_trailing_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        callback_rate: Decimal,
    ) -> NewAlgoOrderResponse:
        """Place a trailing stop without blocking the caller's event loop."""
        logger.info(
            "Submitting Binance trailing stop order "
            "symbol=%s side=%s quantity=%s callback_rate=%s",
            symbol,
            side,
            quantity,
            callback_rate,
        )
        try:
            response = await asyncio.to_thread(
                self._place_trailing_stop_order_sync,
                symbol,
                side,
                quantity,
                callback_rate,
            )
        except Exception:
            logger.exception(
                "Binance trailing stop request failed "
                "symbol=%s side=%s quantity=%s callback_rate=%s",
                symbol,
                side,
                quantity,
                callback_rate,
            )
            raise

        logger.info(
            "Binance trailing stop accepted symbol=%s side=%s algo_id=%s",
            symbol,
            side,
            response.algo_id,
        )
        return response

    def _place_trailing_stop_order_sync(self,
        symbol: str,
        side: str,
        quantity: Decimal,
        callback_rate: Decimal,
    ) -> NewAlgoOrderResponse:
        return self.client.rest_api.new_algo_order(
            algo_type="CONDITIONAL",
            symbol=symbol,
            side=side,
            type="TRAILING_STOP_MARKET",
            quantity=float(quantity),
            callback_rate=float(callback_rate),
            reduce_only=True,
            working_type="MARK_PRICE",
            new_order_resp_type="RESULT",
        ).data()
