# Architecture Decisions

This file is the source of truth for architectural decisions in this repository. Read it before planning or implementing any new feature.

## Golden Path for Development

1. Read `AGENTS.md` and this file before changing application behavior.
2. Check whether the planned change fits the decisions below.
3. If the change requires a different pattern, or if this file does not define the relevant standard, stop and raise the question for human review.
4. After human confirmation, update this file with the new decision before implementing the feature.
5. Run repository checks after implementation to confirm the code still follows the documented architecture.

## Current System Shape

The application is a Python service that monitors Upbit announcement data and prepares Binance futures trading actions. `main.py` is the runtime entry point. Code under `src/` is organized by responsibility:

- `src/config/` is for all configuration handling. Settings, environment parsing, defaults, and typed configuration models belong here.
- `src/integration/` is for connecting to external services. API clients, SDK setup, request adapters, and exchange-specific calls belong here. For example, Binance connection and raw order API calls should live in a Binance integration module rather than directly inside a service.
- `src/service/` is where single-domain application logic lives. Services coordinate configuration, integrations, validation, and workflows for their own concern. A trade placement service may inherit from or compose a Binance integration, but service classes should not directly import unrelated service classes to decide what cross-service action happens next.
- `src/interface/` is where runtime composition lives. Interface modules wire services together into application workflows, such as turning a new Upbit notice event into a Binance trade action. This layer owns callbacks, handlers, factories, and other glue code that combines multiple services.
- `src/support/` is for helpers that support the application without owning business logic, such as startup logging, factories, shared utilities, and small infrastructure helpers.

Do not add new top-level folders under `src/` without human review and an update to this file.

Research and strategy analysis live in the root-level `research/` directory. Notebooks may orchestrate experiments, but reusable market-data and simulation logic belongs in typed Python modules there so it can be tested independently. Research code may read public exchange market data but must remain separate from production order-placement controllers and must never place live trades.

## Configuration

Runtime configuration must flow through `src.config.settings.settings`, backed by `pydantic-settings` and `.env`. Services should not read environment variables directly. Secrets such as Binance API keys must remain in `.env` or the deployment secret manager and must not be committed.

## Runtime and Hosting

The application is deployed as a long-running worker process. The runtime entry point remains `main.py`, which configures logging, installs shutdown signal handlers, and starts `ScraperService`. Hosted environments should stop the worker by sending `SIGTERM` or, on ECS, by scaling the service desired count to zero.

`main.py` is responsible for composing runtime workflows from `src/interface/`. Scraper startup should inject the new-notice handler into `ScraperService`; `ScraperService` should only detect and publish new notices through that handler, not decide whether Binance or another downstream action should run.

Container deployments must run the process with `python main.py`. Application logs must be written to stdout/stderr so the hosting platform can forward them to CloudWatch Logs or an equivalent log sink. The shared logging setup must also write to `logs/application.log`, rotate that file daily at UTC midnight, and retain seven daily files by default. The log directory and retention period are environment-driven settings. Deployment secrets must be injected as environment variables from AWS Secrets Manager, SSM Parameter Store, or another secret manager; they must not be included in the container image.

Worker health is measured by a file heartbeat rather than an HTTP endpoint. An asynchronous task refreshes the configured Telegram heartbeat file while the listener is ready or the connected supervisor is making bounded recovery progress. This proves that the application event loop remains responsive without treating a bare connection as subscription readiness. The container health command must fail when the heartbeat is missing or older than the configured maximum age. Process startup must remove any heartbeat left by an earlier run. The maximum age should exceed the heartbeat interval and allow brief application-level reconnect attempts before ECS replaces the task. ECS task definitions must declare the same health command explicitly because ECS does not rely on image-only health-check configuration for service health management.

Telegram subscription readiness is established explicitly after authentication and before the listener is declared ready. Numeric channel references are activated without an entity-resolution RPC. Usernames and URLs are resolved once during controlled startup, and the resolved peer is used to construct the event handler so incoming-update dispatch never performs lazy username resolution. Hosted configuration should prefer Telethon's marked numeric channel ID.

The Telegram supervisor distinguishes connection, channel resolution, readiness, bounded flood-wait recovery, and shutdown states. Reconnect backoff resets only after subscription readiness, not after a bare network connection. A Telegram `FloodWaitError` encountered during controlled startup must be honored with a shutdown-aware wait without disconnect churn.

The heartbeat is a liveness signal rather than an external readiness endpoint. It is refreshed while the listener is ready and while a connected, responsive supervisor is making bounded progress through authentication, channel resolution, or a Telegram-mandated flood wait. `TELEGRAM_READINESS_MAX_WAIT_SECONDS` limits this degraded-health allowance; after that duration the heartbeat is no longer refreshed, allowing ECS replacement. Listener readiness and health-state transitions must be logged separately.

Trading is guarded by `trading_enabled`. Keep it false for local development unless explicitly testing the Binance order workflow. Production deployments must set `trade_environment`, `trading_enabled`, order settings, scraper settings, and Binance credentials through the deployment environment.

Trade size is configured as a maximum initial-margin budget denominated in the quote asset. The controller selects the greatest integer leverage whose estimated adverse-move capacity exceeds the trailing callback rate plus the applicable maintenance-margin rate and `ORDER_LIQUIDATION_SAFETY_RATE`. Target notional is the margin budget multiplied by that leverage; quantity is rounded down so actual initial margin does not exceed the budget. A continuously connected Binance futures market stream maintains a bounded-age, in-memory price cache. Immediately before entry, the controller must use a fresh streamed price and cached `MARKET_LOT_SIZE`/`MIN_NOTIONAL` filters, round the derived base quantity down to a valid step, and reject missing or stale prices and unavailable, non-trading, undersized, or oversized symbols. Account-specific leverage brackets, including maintenance-margin rates, remain bounded-age metadata. Raw exchange metadata, streaming, leverage-bracket, and leverage-change calls remain in the Binance integration layer.

### Latency Optimization

The approved signal-to-trade latency analysis and implementation plan are recorded in `spec/latency_optimization.md`. Optimization must preserve all trading validations and stop-placement safety.

Binance market rules and account-specific leverage brackets may be cached in memory with bounded freshness, explicit refresh behavior, and safe failure semantics. A symbol missing from cached exchange information must trigger one immediate refresh before rejection. A leverage-change request may be skipped only when controller state confirms that the desired leverage is already set; unknown or invalidated state requires confirmation through Binance.

Market rules and leverage brackets refresh periodically and publish complete cache snapshots atomically. Maintenance REST requests must wait for active or queued trades, while price-stream updates remain independent. A fresh, bounded-age streamed price is read and quantity is calculated locally on the critical path; no REST price request is required. Trailing-stop placement must remain an observed part of the order workflow.

Latency instrumentation must distinguish Telegram receipt, queue wait, handler-to-entry, notice-to-entry, and entry-to-stop timing. Reports must identify nested versus exclusive spans and account for overlapping multi-symbol tasks.

## Coding Best Practices

Prefer clear, explicit dependencies over hidden global state. Use singletons only for stable process-wide infrastructure where repeated construction is wasteful or risky, such as settings or a configured logger. Do not use singletons for workflow services that hold mutable request, polling, order, or account state.

Keep service methods focused on one workflow and integration methods focused on one external capability. Validate inputs at service boundaries before calling integrations. Prefer composition when a service needs multiple dependencies; inheritance is acceptable when a service is intentionally extending one integration, such as a trade service building on Binance connectivity.

Cross-service orchestration belongs in `src/interface/`, not inside individual services. If the action taken for a scraper event changes from Binance trading to another action, the change should be made by replacing the injected handler or interface composition, not by editing `ScraperService`.

Use typed function signatures for public service and integration methods. Raise explicit exceptions for invalid trading inputs rather than returning ambiguous values. Avoid importing from `src/service/` inside `src/integration/` to keep external connectivity independent from business logic.

## Coding Style & Naming Conventions

Use standard Python style with 4-space indentation. Prefer explicit imports and keep service classes in `src/service/` named after their workflow concern. Use `snake_case` for functions, variables, and settings fields; use `PascalCase` for classes. Keep configuration access centralized through `src.config.settings.settings` rather than reading environment variables directly in services. Put external API details in `src/integration/`, not in service methods.

## Test Architecture

- `tests/unit/` tests one function or class in isolation; collaborators are faked or mocked.
- `tests/integration/` tests multiple application components together while external networks remain isolated.
- `tests/e2e/` tests a complete workflow through its observable outcome while faking external services.

Each tier must be independently discoverable with `unittest`. CI runs the tiers separately. Tests must be deterministic, require no real credentials, and never place live trades.
