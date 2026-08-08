# Project Vision

This document records the non-technical direction of the project. It should stay current with the product goal, implemented capabilities, and major decisions that affect why the system works the way it does.

## Goal

The project exists to capitalize on the short window between an Upbit listing announcement and the expected market reaction. The intended end state is an always-available AWS-hosted worker that receives relevant Upbit listing signals and automatically places Binance futures trades with minimal delay.

The system should remain easy to control. Once hosted, the operator must be able to start or stop the service at any time and inspect logs to understand what the listener received, what decisions it made, and whether any trade action was attempted.

## Current Direction

The project is being built as a long-running worker rather than a web API. The current signal source is a configured Telegram channel, monitored through a user-authenticated Telethon session. This direction was chosen because the core workflow is event driven: the service waits for new channel messages and reacts internally. Hosting it as a worker keeps the runtime simpler, cheaper, and closer to the actual job it performs.

The preferred AWS direction is a single-container ECS Fargate service. ECS provides a clean start/stop model through desired count, sends logs to CloudWatch, and avoids managing a server directly. A small Lightsail instance remains the cheapest possible option, but it carries more operational responsibility.

Strategy parameters will be evaluated offline in a dedicated research workspace. Historical Binance Futures trade data will be replayed to compare entry latency and trailing-stop behavior before those findings are considered for production trading changes.

Signal-to-trade latency will be optimized according to `spec/latency_optimization.md`. The current measured DEMO path is dominated by serial Binance metadata and configuration requests rather than parsing. The worker maintains a live Binance futures market-price stream, caches bounded-lifetime market rules and leverage brackets, avoids only confirmed redundant leverage changes, and calculates quote-notional quantity locally immediately before entry. Missing or stale streamed prices fail closed.

Latency improvements must not remove bounded-age streamed-price sizing, market-rule validation, leverage safety, or observable trailing-stop placement. Production rollout remains subject to explicit review and comparison against repeated DEMO measurements rather than a single favorable result.

## Implemented Capabilities

The worker can subscribe to new messages from one configured Telegram channel. The channel may be configured as a username, URL, or numeric channel ID. Telethon events are converted into an integration-neutral message model and placed on a bounded in-memory queue. Messages are processed sequentially, and a failure while handling one message is logged without terminating the listener.

The Telegram connection uses Telethon's automatic reconnect support plus an application-level exponential-backoff supervisor. It uses a serialized Telegram session supplied through configuration and drains messages already accepted into the queue during graceful shutdown.

The Binance controller supports USDT-margined futures on Binance testnet (`DEMO`) or production (`PROD`). Trade size is configured as a quote-asset initial-margin budget. The controller uses the trailing callback rate, Binance maintenance-margin bracket, and an explicit liquidation safety distance to select leverage and derive the target position notional. It validates the symbol and exchange sizing rules, rounds the base quantity down to the valid market-order step, and validates the `BUY` or `SELL` direction and callback rate from 0.1% through 10%. It places a market entry, verifies that a positive quantity was executed, and then places a reduce-only trailing stop for the executed quantity in the opposite direction using mark price as the working price. Synchronous SDK requests run off the application event loop.

Trading is guarded by `TRADING_ENABLED`, which defaults to false. When disabled, a received message reaches the trade handler but no Binance order request is made.

The end-to-end trade trigger filters Telegram messages for original Upbit KRW listing announcements, rejects follow-up notices with trailing update text, parses one or more listed asset symbols, removes duplicate symbols within a notice, and concurrently attempts the configured Binance futures trade for each unique asset using `ORDER_QUOTE_ASSET` as the quote asset. For every successfully opened order, the worker logs the elapsed time from the Telegram notice timestamp to Binance's entry-order update timestamp. Duplicate-message protection across separate original Telegram messages or process restarts is not yet implemented.

The runtime has been prepared for hosted operation. It logs to stdout and to daily rotating local files retained for seven days by default, handles shutdown signals, can be packaged in a Docker container, and uses environment-driven configuration so AWS can inject runtime settings and secrets.

The hosted worker exposes Telegram listener health without adding a web server. While the listener is ready or the connected supervisor is making bounded recovery progress, the responsive application event loop refreshes a local heartbeat. The container becomes unhealthy when that heartbeat is missing or stale, allowing ECS to replace a worker that remains alive but is disconnected or no longer making progress.

Telegram listener startup resolves and activates its configured subscription before reporting readiness. Hosted workers should use a numeric channel ID to avoid repeated username-resolution requests. When Telegram imposes a temporary flood wait, the responsive supervisor honors that delay without reconnect churn and remains live for a bounded configurable period; readiness and degraded recovery remain visible in logs.

The signal-to-trade workflow is modular. `TelegramIntegration` owns external Telegram connectivity, `TelegramController` owns subscription, buffering, and sequential message dispatch, and the interface layer injects the trade handler. `BinanceController` owns trade validation and order sequencing, while `BinanceIntegration` owns raw SDK calls.

## Rationale

The architecture separates signal transport from action so future behavior can change without rewriting Telegram connectivity. If a message should later be classified, send an alert, write to a database, place trades on another exchange, or run multiple actions, that change belongs in the controller or interface layer by replacing or extending the injected handler.

Trading is disabled by default because order placement is high risk. The system should be safe during local development and explicit about when automated trading is enabled.

Configuration is centralized so local `.env` values and hosted environment variables behave consistently. Secrets should never be committed or baked into the container image.

Logs are treated as a primary operating interface. Since this is a headless worker, logs must clearly show startup, Telegram connection and subscription state, health, message-processing failures, trading decisions, order attempts, and failures.

## Direction To Preserve

Keep the project focused on fast, reliable signal reception and controlled trade execution. Avoid adding an API, dashboard, database, or extra infrastructure unless it directly supports reliability, safety, observability, or operational control.

Keep integrations and controllers modular. External-service details belong in `src/integration/`, application coordination belongs in `src/control/`, and cross-component runtime composition belongs in `src/interface/`.

Keep production safety explicit. Before enabling live trading, implement and review message relevance checks, symbol extraction, duplicate-message protection across restarts, order sizing safeguards, symbol availability checks, partial-fill handling, failure recovery when entry succeeds but stop placement fails, and production credential handling.

## Maintenance Rule

This document must always reflect the current direction of the project. After any critical change to product behavior, hosting direction, trading behavior, safety posture, or cross-service workflow, update this file in the same change set.
