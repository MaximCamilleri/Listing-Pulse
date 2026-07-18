from decimal import Decimal
from pathlib import Path
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
    log_directory: Path = Field(
        default=Path("logs"),
        description="Directory where rotating application log files are stored",
    )
    log_retention_days: int = Field(
        default=7,
        ge=1,
        description="Number of daily application log files to retain",
    )

    # Telegram
    telegram_api_id:int = Field(gt=0, description="Numeric application identifier issued by Telegram")
    telegram_api_hash:str = Field(default="", description="Secret application hash issued alongside telegram_api_id")
    telegram_channel:str = Field(default="", description="Telegram channel to monitor")
    telegram_phone:str = Field(default="", description="Phone number of the Telegram user account used by Telethon to authenticate, including the international country code")
    telegram_connection_retries:int = Field(default=5, gt=0, description="Maximum number of connection attempts Telethon performs after a connection failure")
    telegram_retry_delay:float = Field(default=5.0, gt=0.0, description="Number of seconds Telethon waits between its internal connection retry attempts")
    telegram_supervisor_initial_delay:float = Field(default=2.0, gt=0.0, description="Initial number of seconds the application-level supervisor waits before reconnecting after Telethon disconnects")
    telegram_supervisor_max_delay:float = Field(default=60.0, gt=0.0, description="Maximum number of seconds allowed for the application-level exponential reconnection delay")
    
    # Trade
    order_direction: ORDER_DIRECTION = Field(default="BUY", description="Trade direction")
    order_quantity: Decimal = Field(default=Decimal("0"), description="Order quantity")
    order_callback_rate: Decimal = Field(default=Decimal(5), description=f"Trailing stop distance. 5 means 5% off price")
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

    # Binance
    binance_api_key: str = Field(default="", description="")
    binance_api_secret: str = Field(default="", description="")


settings = Settings()
