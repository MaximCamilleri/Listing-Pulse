import threading
import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from src.config.settings import settings
from scripts.place_trade import place_configured_trade
from scripts.run_scraper import run_scraper


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.original_settings = {
            "trading_enabled": settings.trading_enabled,
            "trade_environment": settings.trade_environment,
            "order_direction": settings.order_direction,
            "order_quantity": settings.order_quantity,
            "order_callback_rate": settings.order_callback_rate,
        }

    def tearDown(self):
        for name, value in self.original_settings.items():
            setattr(settings, name, value)

    @patch("scripts.place_trade.configure_logging")
    @patch("scripts.place_trade.BinanceService")
    def test_place_trade_uses_configured_binance_service(
        self,
        binance_service_class,
        _configure_logging,
    ):
        settings.trading_enabled = True
        settings.trade_environment = "DEMO"
        settings.order_direction = "BUY"
        settings.order_quantity = Decimal("2")
        settings.order_callback_rate = Decimal("1.5")
        service = binance_service_class.return_value

        place_configured_trade("BTCUSDT")

        service.place_market_order.assert_called_once_with(
            symbol="BTCUSDT",
            quantity=Decimal("2"),
            direction="BUY",
            callback_rate=Decimal("1.5"),
        )

    @patch("scripts.place_trade.configure_logging")
    @patch("scripts.place_trade.BinanceService")
    def test_place_trade_refuses_when_trading_is_disabled(
        self,
        binance_service_class,
        _configure_logging,
    ):
        settings.trading_enabled = False

        with self.assertRaises(RuntimeError):
            place_configured_trade("BTCUSDT")

        binance_service_class.assert_not_called()

    @patch("scripts.run_scraper._configure_shutdown_signals")
    @patch("scripts.run_scraper.configure_logging")
    @patch("scripts.run_scraper.ScraperService")
    def test_run_scraper_does_not_install_notice_handler(
        self,
        scraper_service_class,
        _configure_logging,
        _configure_signals,
    ):
        stop_event = threading.Event()
        scraper = Mock()
        scraper_service_class.return_value = scraper

        run_scraper(stop_event=stop_event)

        scraper_service_class.assert_called_once_with(stop_event=stop_event)
        scraper.start.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
