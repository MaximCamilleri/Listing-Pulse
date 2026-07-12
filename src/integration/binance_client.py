from decimal import Decimal
from typing import Any

from binance_common.configuration import ConfigurationRestAPI
from binance_sdk_derivatives_trading_usds_futures.derivatives_trading_usds_futures import (
    DerivativesTradingUsdsFutures,
)

from src.config.settings import settings


class BinanceClient:
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

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
    ) -> dict[str, Any]:
        return self.client.rest_api.new_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=float(quantity),
            reduce_only=False,
            new_order_resp_type="RESULT",
        ).data()

    def place_trailing_stop_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        callback_rate: Decimal,
    ) -> dict[str, Any]:
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
