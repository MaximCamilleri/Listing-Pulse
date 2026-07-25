# Upbit Listing Trader

A long-running Python worker that listens for Upbit KRW listing announcements from a configured Telegram channel and opens Binance USD-M Futures trades for the listed assets.

The trade path uses a live Binance price stream for local quote-notional sizing, cached market rules and leverage brackets, confirmed leverage state, and an immediately observed trailing stop. Trading is disabled by default.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` with the required Telegram credentials and runtime settings:

```env
TELEGRAM_SESSION=""
TELEGRAM_API_ID=1
TELEGRAM_API_HASH=""
TELEGRAM_CHANNEL=""
TELEGRAM_PHONE=""

TRADING_ENABLED=false
TRADE_ENVIRONMENT=DEMO
ORDER_DIRECTION=BUY
ORDER_QUOTE_AMOUNT=100
ORDER_CALLBACK_RATE=5
ORDER_QUOTE_ASSET=USDT

BINANCE_API_KEY=""
BINANCE_API_SECRET=""
```

Keep `TRADING_ENABLED=false` and `TRADE_ENVIRONMENT=DEMO` until production trading has been explicitly reviewed.

## Run

```bash
python main.py
```

For detailed latency instrumentation:

```bash
python latency_monitor_main.py
```

Logs are written to stdout and rotating files under `logs/`. The Telegram connection maintains `logs/heartbeat` for container health checks.

## Tests

```bash
python -m unittest discover -s tests/unit -p "test_*.py"
python -m unittest discover -s tests/integration -p "test_*.py"
python -m unittest discover -s tests/e2e -p "test_*.py"
```

Architecture, product direction, and latency decisions are documented in [`spec/architecture.md`](spec/architecture.md), [`spec/vision.md`](spec/vision.md), and [`spec/latency_optimization.md`](spec/latency_optimization.md).
