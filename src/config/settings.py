from decimal import Decimal
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENVIRONMENT = Literal["DEMO", "PROD"]
LOG_LEVEL = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
ORDER_DIRECTION = Literal["BUY", "SELL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="",
        populate_by_name=True,
    )

    # General
    trading_enabled: bool = Field(
        default=False,
        description="When true, new scraper notices trigger Binance order placement",
    )
    trade_environment: ENVIRONMENT = Field(
        default="DEMO",
        description="Defines where trades will be placed. Value can be set to DEMO or PROD",
    )
    log_level: LOG_LEVEL = Field(
        default="INFO",
        description="Minimum log level emitted by the application",
    )
    
    # Trade
    order_direction: ORDER_DIRECTION = Field(default="BUY", description="Trade direction")
    order_quantity: Decimal = Field(default=Decimal("0"), description="Order quantity")
    order_callback_rate: Decimal = Field(default=Decimal(5), description="Trailing stop distance")
    binance_symbol_quote_asset: str = Field(
        default="USDT",
        description="Quote asset appended to parsed notice symbols for Binance futures",
    )
    notice_symbol_pattern: str = Field(
        default="",
        description=(
            "Optional regex used to parse the base asset from a notice title. "
            "Use a named 'symbol' group or the first capture group."
        ),
    )

    # Scraper
    scraper_url: str = Field(default="", description="Upbit announcements API URL")
    scraper_search_term: str = Field(default="", description="Notice title search term")
    scraper_cooldown: float = Field(
        default=10.0,
        description="Time between checks in seconds",
    )
    scraper_cooldown_offset: float = Field(
        default=2.5,
        description="Plus or minus seconds from scraper_cooldown",
    )
    scraper_timeout: float = Field(
        default=5.0,
        description="Max time the scraper can take to respond",
    )

    # Binance
    binance_api_key: str = Field(default="", description="")
    binance_api_secret: str = Field(default="", description="")


settings = Settings()
