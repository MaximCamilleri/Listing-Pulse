# Project Vision

This document records the non-technical direction of the project. It should stay current with the product goal, implemented capabilities, and major decisions that affect why the system works the way it does.

## Goal

The project exists to capitalize on the short window between an Upbit listing announcement and the expected market reaction. The intended end state is an always-available AWS-hosted worker that detects relevant Upbit notices and automatically prepares or places Binance futures trades with minimal delay.

The system should remain easy to control. Once hosted, the operator must be able to start or stop the service at any time and inspect logs to understand what the scraper saw, what decisions it made, and whether any trade action was attempted.

## Current Direction

The project is being built as a long-running worker rather than a web API. That direction was chosen because the core workflow is not request/response driven: the service continuously monitors Upbit, identifies new notices, and reacts internally. Hosting it as a worker keeps the runtime simpler, cheaper, and closer to the actual job it performs.

The preferred AWS direction is a single-container ECS Fargate service. ECS provides a clean start/stop model through desired count, sends logs to CloudWatch, and avoids managing a server directly. A small Lightsail instance remains the cheapest possible option, but it carries more operational responsibility.

## Implemented Capabilities

The scraper can poll the Upbit announcements API, establish a baseline of already-seen notices, and detect new notices without repeatedly acting on the same notice during a single process run.

The Binance service can validate and place a market entry order, confirm that the entry filled, and then place a trailing stop order in the opposite direction.

The runtime has been prepared for hosted operation. It logs to stdout, handles shutdown signals, can be packaged in a Docker container, and uses environment-driven configuration so AWS can inject runtime settings and secrets.

The scraper-to-trade workflow is modular. `ScraperService` detects new notices and publishes them through an injected handler. The default interface-layer handler parses symbols from the notice title and calls `BinanceService` only when trading is enabled.

The notice parser supports single-asset and multi-asset Upbit titles. For example, a title such as `Market Support for Livepeer(LPT)(KRW, USDT Market), Pocket Network(POKT)(KRW Market)` is interpreted as two Binance futures symbols: `LPTUSDT` and `POKTUSDT`.

## Rationale

The architecture separates detection from action so future behavior can change without rewriting the scraper. If a new notice should later send an alert, write to a database, place trades on another exchange, or run multiple actions, that change belongs in the interface layer by replacing or extending the injected handler.

Trading is disabled by default because order placement is high risk. The system should be safe during local development and explicit about when automated trading is enabled.

Configuration is centralized so local `.env` values and hosted environment variables behave consistently. Secrets should never be committed or baked into the container image.

Logs are treated as a primary operating interface. Since this is a headless worker, logs must clearly show startup, scraping, notice detection, symbol parsing, trading decisions, order attempts, and failures.

## Direction To Preserve

Keep the project focused on fast, reliable detection and controlled trade execution. Avoid adding an API, dashboard, database, or extra infrastructure unless it directly supports reliability, safety, observability, or operational control.

Keep services modular. Individual services should own one business capability. Cross-service workflows should live in `src/interface/`, where runtime behavior can be swapped without changing the underlying scraper or exchange services.

Keep production safety explicit. Before enabling live trading, duplicate-notice persistence across restarts, order sizing safeguards, symbol availability checks, and production credential handling should be reviewed.

## Maintenance Rule

This document must always reflect the current direction of the project. After any critical change to product behavior, hosting direction, trading behavior, safety posture, or cross-service workflow, update this file in the same change set.
