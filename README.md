# Listing Pulse

Listing Pulse is an event-driven Python worker that turns Upbit KRW listing announcements into validated Binance USD-M Futures orders. It is designed around the engineering constraints of automated execution: low latency, unreliable external connections, exchange-specific order rules, and the need to fail safely.

The project is currently intended for Binance testnet experimentation. Live trading is disabled by default and requires explicit configuration.

## Engineering Highlights

- **Asynchronous event pipeline:** Telethon events are normalized, buffered in a bounded queue, and processed without blocking the event loop. Notices containing multiple assets can trigger concurrent per-symbol workflows.
- **Latency-aware execution:** A live Binance WebSocket stream supplies fresh prices while bounded-age caches hold market rules and leverage brackets, removing three sequential REST requests from the normal trade path.
- **Defensive order handling:** The controller validates symbol status, notional, quantity limits, step size, direction, leverage, and callback rate before entry. It verifies the executed quantity before placing an observed reduce-only trailing stop.
- **Resilient worker lifecycle:** The Telegram supervisor handles reconnects, exponential backoff, flood waits, readiness transitions, queue draining, and graceful shutdown.
- **Production-oriented operations:** The application supports Docker deployment, ECS-compatible heartbeat health checks, structured runtime logging, daily log rotation, and environment-based secret injection.
- **Isolated test architecture:** Unit, integration, and end-to-end tests use mocked external systems and never require credentials or place live trades.

## Execution Flow

```text
Telegram channel
    -> TelegramIntegration (connection and event conversion)
    -> TelegramController (bounded queue and dispatch)
    -> trade interface (announcement filtering and symbol extraction)
    -> BinanceController (validation, sizing, leverage, and order workflow)
    -> BinanceIntegration (WebSocket and REST/SDK calls)
    -> market entry
    -> reduce-only trailing stop
```

Integration modules own exchange and messaging APIs, controllers own domain workflows, and the interface layer composes the end-to-end signal path. This keeps message transport independent from trading behavior and makes each layer testable with fakes.

## Latency Optimization

The original testnet path made five sequential Binance requests before entry: exchange information, symbol price, leverage brackets, leverage configuration, and the market order. Profiling showed that network operations—not message parsing—dominated execution time.

The optimized path:

1. Maintains streamed prices with an explicit freshness limit.
2. Refreshes market rules and leverage brackets outside the critical path.
3. Calculates quote-notional quantity locally immediately before entry.
4. Skips leverage configuration only when the desired state was previously confirmed.
5. Preserves all exchange validations and awaits trailing-stop placement.

A single DEMO observation reduced reported notice-to-entry latency by **52.8%**, from **1,717 ms to 811 ms**, and complete trigger time by **55.1%**, from **1,955 ms to 878 ms**. These figures demonstrate the removal of critical-path requests, not a production latency guarantee: the timestamps have cross-clock limitations, and distribution claims require at least 20 consistent samples.

See [`spec/latency_optimization.md`](spec/latency_optimization.md) for the measurements, limitations, and validation plan.

## Trading Safety

Listing Pulse fails closed when prices or exchange metadata are missing, invalid, or stale. Trade size is configured as quote-asset notional and converted to a valid base quantity using the latest streamed price and Binance market filters.

Additional safeguards include:

- `TRADING_ENABLED=false` by default
- separate `DEMO` and `PROD` environments
- bounded cache freshness and refresh-on-symbol-miss behavior
- confirmed leverage state with periodic reconciliation
- positive-fill verification before stop placement
- reduce-only trailing stops for the executed quantity
- no credentials embedded in source code or container images

Duplicate-message protection across process restarts and recovery from entry-success/stop-failure states remain required before production rollout.

## Technology

Python 3.13, AsyncIO, Telethon, Binance Futures APIs, WebSockets, Pydantic Settings, Docker, and AWS ECS/Fargate.

## Run Locally

Create and activate a virtual environment, then install the dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create a local `.env`:

```env
TELEGRAM_SESSION=""
TELEGRAM_API_ID=1
TELEGRAM_API_HASH=""
TELEGRAM_CHANNEL="-1002562064658"
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

Keep `TRADING_ENABLED=false` and `TRADE_ENVIRONMENT=DEMO` unless live execution has been explicitly reviewed.

Start the worker:

```bash
python main.py
```

Run the instrumented latency workflow:

```bash
python latency_monitor_main.py
```

## Tests

The test suites are independently discoverable and do not access live exchanges:

```bash
python -m unittest discover -s tests/unit -p "test_*.py"
python -m unittest discover -s tests/integration -p "test_*.py"
python -m unittest discover -s tests/e2e -p "test_*.py"
```

## Design Documentation

- [`spec/architecture.md`](spec/architecture.md) defines module boundaries, runtime behavior, testing tiers, and deployment standards.
- [`spec/vision.md`](spec/vision.md) records the product direction and production-safety constraints.
- [`spec/latency_optimization.md`](spec/latency_optimization.md) documents profiling results, optimization decisions, and remaining performance validation.
