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

## Configuration

Runtime configuration must flow through `src.config.settings.settings`, backed by `pydantic-settings` and `.env`. Services should not read environment variables directly. Secrets such as Binance API keys must remain in `.env` or the deployment secret manager and must not be committed.

## Runtime and Hosting

The application is deployed as a long-running worker process. The runtime entry point remains `main.py`, which configures logging, installs shutdown signal handlers, and starts `ScraperService`. Hosted environments should stop the worker by sending `SIGTERM` or, on ECS, by scaling the service desired count to zero.

`main.py` is responsible for composing runtime workflows from `src/interface/`. Scraper startup should inject the new-notice handler into `ScraperService`; `ScraperService` should only detect and publish new notices through that handler, not decide whether Binance or another downstream action should run.

Container deployments must run the process with `python main.py`. Application logs must be written to stdout/stderr so the hosting platform can forward them to CloudWatch Logs or an equivalent log sink. The shared logging setup must also write to `logs/application.log`, rotate that file daily at UTC midnight, and retain seven daily files by default. The log directory and retention period are environment-driven settings. Deployment secrets must be injected as environment variables from AWS Secrets Manager, SSM Parameter Store, or another secret manager; they must not be included in the container image.

Worker health is measured by a file heartbeat rather than an HTTP endpoint. Each successful Upbit API response must refresh the configured polling heartbeat file. The container health command must fail when that file is missing or older than the scraper cooldown, absolute cooldown offset, request timeout, and configured health-check grace period combined. A process start must remove any heartbeat left by a previous run. ECS task definitions must declare the same health command explicitly because ECS does not rely on image-only health-check configuration for service health management.

Trading is guarded by `trading_enabled`. Keep it false for local development unless explicitly testing the Binance order workflow. Production deployments must set `trade_environment`, `trading_enabled`, order settings, scraper settings, and Binance credentials through the deployment environment.

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
