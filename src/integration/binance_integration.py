import asyncio
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
        logger.info(
            "Submitting Binance market order symbol=%s side=%s quantity=%s",
            symbol,
            side,
            quantity,
        )
        try:
            response = self.client.rest_api.new_order(
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=float(quantity),
                reduce_only=False,
                new_order_resp_type="RESULT",
            ).data()
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
        logger.info(
            "Submitting Binance trailing stop order "
            "symbol=%s side=%s quantity=%s callback_rate=%s",
            symbol,
            side,
            quantity,
            callback_rate,
        )
        try:
            response = self.client.rest_api.new_algo_order(
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