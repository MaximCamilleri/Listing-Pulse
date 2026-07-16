import re
from collections.abc import Callable
from typing import Any

from src.config.settings import settings
from src.control.binance_service import BinanceService
from src.support.logger import get_logger


logger = get_logger(__name__)

IGNORED_SYMBOL_TOKENS = {
    "BTC",
    "ETH",
    "KRW",
    "USDT",
    "MARKET",
    "MARKETS",
    "PAIR",
    "PAIRS",
}


def create_notice_trade_handler(
    binance_service: BinanceService | None = None,
) -> Callable[[dict[str, Any]], None]:
    """
    Compose the new-notice event from the scraper into the Binance trade action.

    The scraper service stays exchange-agnostic by calling only the returned
    handler. Binance setup remains lazy so disabled trading does not initialize
    the SDK or require credentials.
    """
    configured_binance_service = binance_service

    def handle_notice(notice: dict[str, Any]) -> None:
        nonlocal configured_binance_service

        notice_id = notice.get("id")
        title = notice.get("title", "")

        if not settings.trading_enabled:
            logger.info(
                "Trading disabled; skipping Binance order notice_id=%s title=%s",
                notice_id,
                title,
            )
            return

        symbols = extract_binance_symbols(title)
        if not symbols:
            logger.error(
                "Could not derive Binance symbols from notice notice_id=%s title=%s",
                notice_id,
                title,
            )
            return

        if configured_binance_service is None:
            configured_binance_service = BinanceService()

        for symbol in symbols:
            logger.info(
                "New Upbit notice triggering Binance order "
                "notice_id=%s title=%s symbol=%s direction=%s quantity=%s",
                notice_id,
                title,
                symbol,
                settings.order_direction,
                settings.order_quantity,
            )
            configured_binance_service.place_market_order(
                symbol=symbol,
                quantity=settings.order_quantity,
                direction=settings.order_direction,
                callback_rate=settings.order_callback_rate,
            )

    return handle_notice


def extract_binance_symbol(title: str) -> str | None:
    symbols = extract_binance_symbols(title)
    if not symbols:
        return None

    return symbols[0]


def extract_binance_symbols(title: str) -> list[str]:
    base_assets = extract_notice_base_assets(title)
    quote_asset = settings.binance_symbol_quote_asset.upper().strip()
    if not quote_asset:
        logger.error("Cannot build Binance symbol with empty quote asset")
        return []

    symbols = []
    for base_asset in base_assets:
        if base_asset.endswith(quote_asset):
            symbols.append(base_asset)
        else:
            symbols.append(f"{base_asset}{quote_asset}")

    return symbols


def extract_notice_base_asset(title: str) -> str | None:
    base_assets = extract_notice_base_assets(title)
    if not base_assets:
        return None

    return base_assets[0]


def extract_notice_base_assets(title: str) -> list[str]:
    if settings.notice_symbol_pattern:
        return _extract_symbols_with_pattern(title)

    symbols = []
    seen_symbols = set()

    parenthesized_tokens = re.findall(r"\(([A-Z0-9,\s]+)\)", title.upper())
    for token_group in parenthesized_tokens:
        for token in re.split(r"[\s,]+", token_group):
            symbol = _clean_symbol(token)
            if symbol is not None and symbol not in seen_symbols:
                symbols.append(symbol)
                seen_symbols.add(symbol)

    if symbols:
        return symbols

    for token in re.findall(r"\b[A-Z0-9]{2,10}\b", title.upper()):
        symbol = _clean_symbol(token)
        if symbol is not None and symbol not in seen_symbols:
            symbols.append(symbol)
            seen_symbols.add(symbol)

    return symbols


def _extract_symbols_with_pattern(title: str) -> list[str]:
    symbols = []
    seen_symbols = set()

    for match in re.finditer(settings.notice_symbol_pattern, title):
        symbol = match.groupdict().get("symbol")
        if symbol is None and match.groups():
            symbol = match.group(1)

        cleaned_symbol = _clean_symbol(symbol)
        if cleaned_symbol is not None and cleaned_symbol not in seen_symbols:
            symbols.append(cleaned_symbol)
            seen_symbols.add(cleaned_symbol)

    return symbols


def _clean_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None

    cleaned = re.sub(r"[^A-Z0-9]", "", symbol.upper().strip())
    if len(cleaned) < 2 or cleaned in IGNORED_SYMBOL_TOKENS:
        return None

    return cleaned
