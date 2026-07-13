import logging
import unittest
from decimal import Decimal

from src.config.settings import settings
from src.interface.notice_trading_workflow import (
    create_notice_trade_handler,
    extract_binance_symbol,
    extract_binance_symbols,
)


class FakeBinanceService:
    def __init__(self):
        self.orders = []

    def place_market_order(self, symbol, quantity, direction, callback_rate):
        self.orders.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "direction": direction,
                "callback_rate": callback_rate,
            }
        )
        return {"orderId": 100}, {"orderId": 101}


class NoticeTradingWorkflowTests(unittest.TestCase):
    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.original_settings = {
            "trading_enabled": settings.trading_enabled,
            "order_direction": settings.order_direction,
            "order_quantity": settings.order_quantity,
            "order_callback_rate": settings.order_callback_rate,
            "binance_symbol_quote_asset": settings.binance_symbol_quote_asset,
            "notice_symbol_pattern": settings.notice_symbol_pattern,
        }

    def tearDown(self):
        for name, value in self.original_settings.items():
            setattr(settings, name, value)
        logging.disable(logging.NOTSET)

    def test_handler_does_not_place_order_when_trading_disabled(self):
        settings.trading_enabled = False
        binance_service = FakeBinanceService()
        handle_notice = create_notice_trade_handler(binance_service=binance_service)

        handle_notice({"id": 10, "title": "New KRW Market listing (ABC)"})

        self.assertEqual(binance_service.orders, [])

    def test_handler_places_order_when_trading_enabled(self):
        settings.trading_enabled = True
        settings.order_direction = "BUY"
        settings.order_quantity = Decimal("25")
        settings.order_callback_rate = Decimal("1.5")
        settings.binance_symbol_quote_asset = "USDT"
        settings.notice_symbol_pattern = ""
        binance_service = FakeBinanceService()
        handle_notice = create_notice_trade_handler(binance_service=binance_service)

        handle_notice({"id": 10, "title": "New KRW Market listing (ABC)"})

        self.assertEqual(
            binance_service.orders,
            [
                {
                    "symbol": "ABCUSDT",
                    "quantity": Decimal("25"),
                    "direction": "BUY",
                    "callback_rate": Decimal("1.5"),
                }
            ],
        )

    def test_handler_places_one_order_per_symbol_in_multi_asset_notice(self):
        settings.trading_enabled = True
        settings.order_direction = "BUY"
        settings.order_quantity = Decimal("25")
        settings.order_callback_rate = Decimal("1.5")
        settings.binance_symbol_quote_asset = "USDT"
        settings.notice_symbol_pattern = ""
        binance_service = FakeBinanceService()
        handle_notice = create_notice_trade_handler(binance_service=binance_service)

        handle_notice(
            {
                "id": 11,
                "title": (
                    "Market Support for Livepeer(LPT)(KRW, USDT Market), "
                    "Pocket Network(POKT)(KRW Market)"
                ),
            }
        )

        self.assertEqual(
            binance_service.orders,
            [
                {
                    "symbol": "LPTUSDT",
                    "quantity": Decimal("25"),
                    "direction": "BUY",
                    "callback_rate": Decimal("1.5"),
                },
                {
                    "symbol": "POKTUSDT",
                    "quantity": Decimal("25"),
                    "direction": "BUY",
                    "callback_rate": Decimal("1.5"),
                },
            ],
        )

    def test_custom_notice_symbol_pattern_can_parse_symbol(self):
        settings.notice_symbol_pattern = r"asset=(?P<symbol>[A-Z0-9]+)"

        symbol = extract_binance_symbol("listing notice asset=XYZ")

        self.assertEqual(symbol, "XYZUSDT")

    def test_multi_asset_notice_parses_trade_symbols(self):
        title = (
            "Market Support for Livepeer(LPT)(KRW, USDT Market), "
            "Pocket Network(POKT)(KRW Market)"
        )

        symbols = extract_binance_symbols(title)

        self.assertEqual(symbols, ["LPTUSDT", "POKTUSDT"])


if __name__ == "__main__":
    unittest.main()
