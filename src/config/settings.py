from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENVIRONMENT = Literal["DEMO", "PROD"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="",
        populate_by_name=True,
    )

    # General
    trade_environment: ENVIRONMENT = Field(
        default="DEMO",
        description="Defines where trades will be placed. Value can be set to DEMO or PROD",
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
