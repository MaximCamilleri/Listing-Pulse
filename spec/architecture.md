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
- `src/service/` is where application logic lives. Services coordinate configuration, integrations, validation, and workflows. A trade placement service may inherit from or compose a Binance integration, but business decisions stay in the service layer.
- `src/support/` is for helpers that support the application without owning business logic, such as startup logging, factories, shared utilities, and small infrastructure helpers.

Do not add new top-level folders under `src/` without human review and an update to this file.

## Configuration

Runtime configuration must flow through `src.config.settings.settings`, backed by `pydantic-settings` and `.env`. Services should not read environment variables directly. Secrets such as Binance API keys must remain in `.env` or the deployment secret manager and must not be committed.

## Coding Best Practices

Prefer clear, explicit dependencies over hidden global state. Use singletons only for stable process-wide infrastructure where repeated construction is wasteful or risky, such as settings or a configured logger. Do not use singletons for workflow services that hold mutable request, polling, order, or account state.

Keep service methods focused on one workflow and integration methods focused on one external capability. Validate inputs at service boundaries before calling integrations. Prefer composition when a service needs multiple dependencies; inheritance is acceptable when a service is intentionally extending one integration, such as a trade service building on Binance connectivity.

Use typed function signatures for public service and integration methods. Raise explicit exceptions for invalid trading inputs rather than returning ambiguous values. Avoid importing from `src/service/` inside `src/integration/` to keep external connectivity independent from business logic.

## Coding Style & Naming Conventions

Use standard Python style with 4-space indentation. Prefer explicit imports and keep service classes in `src/service/` named after their workflow concern. Use `snake_case` for functions, variables, and settings fields; use `PascalCase` for classes. Keep configuration access centralized through `src.config.settings.settings` rather than reading environment variables directly in services. Put external API details in `src/integration/`, not in service methods.

