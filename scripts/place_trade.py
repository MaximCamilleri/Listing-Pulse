import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import settings
from control.binance_controler import BinanceService
from src.support.logger import configure_logging, get_logger


logger = get_logger(__name__)


def place_configured_trade(symbol: str) -> None:
    """Place one configured Binance trade for an explicitly supplied symbol."""
    configure_logging()

    if not settings.trading_enabled:
        logger.error("Trading is disabled; set TRADING_ENABLED=true to place an order")
        raise RuntimeError("Trading is disabled. Set TRADING_ENABLED=true to place an order.")

    logger.info(
        "Starting manual Binance trade symbol=%s environment=%s direction=%s quantity=%s",
        symbol,
        settings.trade_environment,
        settings.order_direction,
        settings.order_quantity,
    )
    BinanceService().place_market_order(
        symbol=symbol,
        quantity=settings.order_quantity,
        direction=settings.order_direction,
        callback_rate=settings.order_callback_rate,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Place one Binance futures trade using the configured order settings."
    )
    parser.add_argument("symbol", help="Binance futures symbol, for example BTCUSDT")
    return parser.parse_args()


if __name__ == "__main__":
    place_configured_trade(_parse_args().symbol)
