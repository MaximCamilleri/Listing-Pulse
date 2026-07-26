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
    trading_enabled: bool = Field(default=False, description="When true, new scraper notices trigger Binance order placement")
    trade_environment: ENVIRONMENT = Field(default="DEMO", description="Defines where trades will be placed. Value can be set to DEMO or PROD")
    log_level: LOG_LEVEL = Field(default="INFO", description="Minimum log level emitted by the application")
    log_directory: Path = Field(default=Path("logs"), description="Directory where rotating application log files are stored")
    log_retention_days: int = Field(default=7, ge=1, description="Number of daily application log files to retain")

    # Health
    healthcheck_file: Path = Field(default=Path("logs/heartbeat"), description="Heartbeat refreshed while the Telegram listener is ready or making bounded recovery progress")
    healthcheck_interval_seconds: float = Field(default=15.0, gt=0.0, description="Seconds between Telegram connection heartbeat updates")
    healthcheck_max_age_seconds: float = Field(default=90.0, gt=0.0, description="Maximum heartbeat age before the worker is unhealthy")

    # Telegram
    telegram_session:str = Field(default="", description="Serialized Telethon session")
    telegram_api_id:int = Field(default=1, gt=0, description="Numeric application identifier issued by Telegram")
    telegram_api_hash:str = Field(default="", description="Secret application hash issued alongside telegram_api_id")
    telegram_channel:str = Field(default="", description="Telegram channel to monitor")
    telegram_phone:str = Field(default="", description="Phone number of the Telegram user account used by Telethon to authenticate, including the international country code")
    telegram_connection_retries:int = Field(default=5, gt=0, description="Maximum number of connection attempts Telethon performs after a connection failure")
    telegram_retry_delay:float = Field(default=5.0, gt=0.0, description="Number of seconds Telethon waits between its internal connection retry attempts")
    telegram_supervisor_initial_delay:float = Field(default=2.0, gt=0.0, description="Initial number of seconds the application-level supervisor waits before reconnecting after Telethon disconnects")
    telegram_supervisor_max_delay:float = Field(default=60.0, gt=0.0, description="Maximum number of seconds allowed for the application-level exponential reconnection delay")
    telegram_readiness_max_wait_seconds:float = Field(default=900.0, gt=0.0, description="Maximum time a connected listener may remain in recoverable startup or flood-wait state while refreshing health")

    # Trade
    order_direction: ORDER_DIRECTION = Field(default="BUY", description="Trade direction")
    order_quote_amount: Decimal = Field(default=Decimal("0"), ge=0, description="Target position notional denominated in the symbol's quote asset")
    order_callback_rate: Decimal = Field(default=Decimal(5), description=f"Trailing stop distance. 5 means 5% off price")
    order_quote_asset: str = Field(default="USDT", description="Quote asset appended to parsed notice symbols for Binance futures")

    # Binance
    binance_api_key: str = Field(default="", description="")
    binance_api_secret: str = Field(default="", description="")
    binance_price_max_age_seconds: float = Field(default=2.5, gt=0, description="Maximum age of a streamed Binance price used for order sizing")
    binance_env_refresh_interval_seconds: float = Field(default=900.0, gt=0, description="Seconds between Binance market-rule and leverage-bracket refreshes")
    binance_env_max_age_seconds: float = Field(default=3600.0, gt=0, description="Maximum age of cached Binance trading metadata")
    binance_leverage_reconcile_seconds: float = Field(default=3600.0, gt=0, description="Maximum age of controller-confirmed Binance leverage state")


settings = Settings()
