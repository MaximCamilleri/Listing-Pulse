# Listing Pulse

Listing Pulse is an event-driven Python worker that turns Upbit KRW listing announcements into validated Binance USD-M Futures orders. It is designed around the engineering constraints of automated execution: low latency, unreliable external connections, exchange-specific order rules, and the need to fail safely.

The project is currently intended for Binance testnet experimentation. Live trading is disabled by default and requires explicit configuration.

## Generate a Telegram Session

From the repository root, with the project dependencies installed, set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in `.env` using your credentials from [Telegram's application portal](https://my.telegram.org). Set `TELEGRAM_PHONE` with its international country code, or enter it when prompted.

```powershell
python script/generate_telegram_session.py
```

Enter the Telegram login code and, if enabled, your two-step verification password. Copy the printed `TELEGRAM_SESSION="..."` line into `.env` or your deployment secret configuration, then restart the worker. The script always creates a fresh session and ignores any existing `TELEGRAM_SESSION`; it does not modify `.env` or start the trading workflow.

Generate a separate session for each independently running worker instead of sharing a session between deployments. Keep the output private: a [Telethon string session](https://docs.telethon.dev/en/stable/concepts/sessions.html#string-sessions) grants access to the Telegram account. Stop any old worker before replacing its session configuration.

## Select Event and Trade Sources

`python main.py` automatically starts a listener for each non-blank `UPBIT_TELEGRAM_CHANNEL` and `BITHUMB_TELEGRAM_CHANNEL` setting. Set both to listen to both sources, or leave one blank to disable it. Startup fails if neither is configured. When calling `start_trader` directly, you can select pairs explicitly:

```python
asyncio.run(start_trader(
    stop_event=shutdown_event,
    combinations=[("UPBIT", "BINANCE"), ("BITHUMB", "BINANCE")],
))
```

The listeners run concurrently and share one Binance controller. A shutdown request or either listener exiting stops the group and drains accepted messages before closing Binance. Empty lists, unsupported sources, and duplicate pairs are rejected. Omit `combinations` to use the Upbit/Binance default; a single pair selects one source. `start_trader` accepts only `stop_event` and `combinations`. Separate notices from different sources can each trigger trades; the current shared heartbeat reports progress from either listener rather than health of every listener.

## Engineering Highlights

## Select Event and Trade Sources

`start_trader()` defaults to Upbit signals and Binance trades. To listen to both sources, set `UPBIT_TELEGRAM_CHANNEL` and `BITHUMB_TELEGRAM_CHANNEL`, then use this call in `main.py` after configuring the shutdown event:

```python
asyncio.run(start_trader(
    stop_event=shutdown_event,
    combinations=[("UPBIT", "BINANCE"), ("BITHUMB", "BINANCE")],
))
```

The listeners run concurrently and share one Binance controller. A shutdown request or either listener exiting stops the group and drains accepted messages before closing Binance. Empty lists, unsupported sources, and duplicate pairs are rejected. Omit `combinations` to use the Upbit/Binance default; a single pair selects one source. `start_trader` accepts only `stop_event` and `combinations`. Separate notices from different sources can each trigger trades; the current shared heartbeat reports progress from either listener rather than health of every listener.

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

Listing Pulse fails closed when prices or exchange metadata are missing, invalid, or stale. Trade size is configured as a quote-asset initial-margin budget. The controller selects leverage that allows for the trailing callback, Binance maintenance margin, and the configured liquidation safety distance, then converts the resulting notional to a valid base quantity using the latest streamed price and Binance market filters.

### Entry Size and Leverage

For each symbol, the controller chooses the greatest whole-number leverage that is permitted by the applicable Binance notional bracket and satisfies the following conservative condition:

```text
1 / leverage > callback rate + liquidation safety rate + maintenance margin rate
```

Rates are expressed as fractions in this calculation. For example, a 5% callback, 1% safety allowance, and 1% maintenance margin require more than 7% adverse-move capacity. The highest qualifying leverage is 14x because `1 / 14 = 7.14%`, while `1 / 15 = 6.67%` does not qualify. Binance's advertised maximum leverage is only an upper limit; the controller may select less leverage to keep the estimated liquidation boundary beyond the trailing-stop callback and safety allowance.

The configured margin budget and selected leverage determine the target entry notional:

```text
target notional = ORDER_MARGIN_AMOUNT * selected leverage
raw quantity = target notional / current streamed price
```

With `ORDER_MARGIN_AMOUNT=200` and 14x leverage, the target notional is `2,800 USDT`. The raw base-asset quantity is rounded down to Binance's valid market-order step and checked against the symbol's quantity and minimum-notional filters. Rounding down means the actual notional and estimated initial margin can be slightly lower than their configured targets, but not higher.

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
ORDER_MARGIN_AMOUNT=100
ORDER_CALLBACK_RATE=5
ORDER_LIQUIDATION_SAFETY_RATE=1
ORDER_QUOTE_ASSET=USDT

BINANCE_API_KEY=""
BINANCE_API_SECRET=""
```

`ORDER_MARGIN_AMOUNT` replaces `ORDER_QUOTE_AMOUNT`. The legacy name is accepted temporarily as a compatibility alias, but new deployments should use the margin name.

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
