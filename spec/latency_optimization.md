# Signal-to-Trade Latency Optimization

This document records the measured latency of the `_trigger_action` workflow,
the interpretation of those measurements, and the approved implementation plan
for reducing the time between a Telegram notice and a Binance market entry.

## Objective

Reduce notice-to-entry latency without weakening symbol validation, quantity
validation, leverage selection, stop placement, credential handling, or the
default prohibition on unreviewed production trading.

The primary metric is the elapsed time from the Telegram notice timestamp to
Binance's entry-order update timestamp. Handler completion is a secondary
metric because trailing-stop placement occurs after the entry and therefore
does not affect entry latency.

## Measured Baseline

The following DEMO observation was recorded on 2026-07-23 for `SOONUSDT`:

| Measurement | Duration |
| --- | ---: |
| Telegram notice to handler start | 267 ms |
| Exchange information request | 637 ms |
| Symbol price request | 257 ms |
| Leverage brackets request | 259 ms |
| Initial leverage change | 257 ms |
| Market entry request | 262 ms |
| Telegram notice to Binance entry update | 1,717 ms |
| Trailing-stop request after entry | 282 ms |
| Complete `_trigger_action` wall time | 1,955 ms |

Notice parsing and filtering took less than 1 ms and is not a meaningful
optimization target.

The observed pre-entry path performs five sequential Binance requests:

1. Retrieve exchange information.
2. Retrieve the current symbol price.
3. Retrieve account leverage brackets.
4. Set initial leverage.
5. Submit the market entry.

The similar 257–282 ms durations of most Binance operations suggest a common
network or testnet request floor. Exchange information is substantially slower
and is the largest individual optimization opportunity.

### Profiling interpretation

The original report contains nested timings. `size_validation` includes both
`exchange_info` and `price`, while `leverage_selection` includes
`leverage_brackets`. Nested rows must not be added together or treated as
exclusive allocation percentages.

The current `notice_to_handler_seconds` value also combines several sources:
Telegram delivery, Telethon message conversion, queue insertion, and queue
waiting. Additional timestamps are required to separate those components.

One observation is not a sufficient performance baseline. Changes must be
compared using repeated samples and distribution statistics.

## Target Design

### Measurement

Latency instrumentation must report:

- Telegram notice age when the integration callback receives the event.
- Message conversion duration.
- Queue insertion and queue-wait duration.
- Parsing and filtering duration.
- Exclusive duration of each Binance operation.
- Handler-to-entry duration.
- Notice-to-entry duration using Binance's entry update timestamp.
- Entry-to-trailing-stop duration.
- Complete handler wall time.
- Cache hit or miss status for cached operations.
- Whether the measurement used a cold or warm client connection, when known.

Reports must include success or failure status and retain the channel ID,
message ID, and symbol needed to correlate workflow logs. Nested spans may be
reported for context, but the report must clearly distinguish inclusive and
exclusive durations.

Performance comparisons must use at least 20 DEMO observations where practical
and report minimum, median, p90, p95, and maximum latency. Results from notices
containing multiple assets must account for concurrent tasks; their individual
durations may overlap and must not be summed as wall-clock allocation.

### Exchange-information cache

Binance futures market rules must be loaded into an in-memory, symbol-keyed
cache rather than fetched once per order.

- Populate the cache during startup without preventing the worker from
  recovering through the existing reconnect lifecycle.
- Refresh it periodically with a configurable or documented refresh interval.
- If an announced symbol is absent, perform one immediate refresh before
  rejecting it.
- Never use stale rules indefinitely when refreshes fail.
- Continue validating trading status, step size, minimum and maximum quantity,
  and minimum notional before entry.
- Keep raw exchange-information requests in the Binance integration layer and
  cache ownership in the Binance controller or a dedicated support component
  injected into it.

The expected cache-hit saving from the measured sample is approximately
637 ms.

### Leverage-bracket cache

Account-specific leverage brackets may be cached because they are relatively
stable metadata, but they remain account and symbol specific.

- Cache brackets by symbol with a bounded time-to-live.
- Fetch on demand for newly available symbols.
- Refresh after a leverage-related Binance rejection.
- Never substitute an assumed leverage when bracket data is unavailable.
- Continue choosing a bracket that supports the validated intended notional.

The expected cache-hit saving from the measured sample is approximately
259 ms.

### Concurrent independent retrieval

On cache misses, exchange information, current price, and leverage brackets
must be requested concurrently because none depends on the result of another.
Quantity and leverage calculation begin only after their required inputs are
available.

For the measured sample, serial retrieval consumed approximately 1,153 ms.
Concurrent retrieval should approach the slowest request, approximately
637 ms, for a potential cold-path saving near 516 ms.

### Confirmed leverage-state cache

The controller may skip `set_initial_leverage` only when it has confirmed that
the desired leverage is already configured for that symbol.

- Record leverage state only after Binance confirms a successful change.
- Key state by account environment and symbol.
- Invalidate it after leverage-related order errors.
- Provide bounded reconciliation because another process or operator may
  change account state.
- Treat newly listed symbols as unknown until confirmed.
- If state is uncertain, set leverage before entry.

This optimization must favor safe confirmation over latency. The measured
repeat-symbol saving is approximately 257 ms.

### Price and entry requests

A fresh price remains on the critical path because position size is configured
as quote-asset notional. The entry submission is inherently required. These
requests must not be removed or replaced with unvalidated estimates merely to
improve latency.

### Trailing-stop placement

Trailing-stop placement remains immediately after a successful entry. It must
not be detached into an unobserved background task. Doing so would not improve
the entry timestamp and would weaken visibility of the high-risk state in which
an entry exists without its intended stop.

A different stop-placement workflow requires explicit human review and a
documented recovery mechanism for entry-success/stop-failure scenarios.

### Hosting and connection measurements

The repeated approximately 260 ms request floor must be investigated from the
intended hosting environment. Benchmark:

- The current development location.
- The intended AWS region.
- Reasonable alternative AWS regions.
- Cold and warm client connections.
- DEMO endpoints and safe read-only production requests where appropriate.

No production order may be placed for a latency benchmark unless separately
reviewed and explicitly authorized.

## Expected Result

Based on the single measured sample, an exchange-information cache hit could
reduce notice-to-entry latency from approximately 1.72 seconds to approximately
1.08 seconds.

With exchange information and leverage brackets cached, and with an already
confirmed leverage setting, the estimated path is:

| Remaining stage | Estimated duration |
| --- | ---: |
| Telegram delivery to handler | 267 ms |
| Fresh price | 257 ms |
| Market entry | 262 ms |
| Local processing | Approximately 1 ms |
| Estimated notice-to-entry | Approximately 787 ms |

If leverage must be changed, the estimate is approximately 1.04 seconds.
These figures are planning estimates, not acceptance guarantees. DEMO and
production network behavior may differ.

## Implementation Plan

1. Correct the profiler to capture receive, queue, entry, and stop timestamps
   and produce exclusive timing distributions.
2. Establish a repeated DEMO baseline before changing the order workflow.
3. Add the exchange-information cache, periodic refresh, and refresh-on-miss.
4. Add the bounded leverage-bracket cache and rejection invalidation.
5. Fetch independent inputs concurrently on cache misses.
6. Add confirmed leverage-state tracking with conservative invalidation and
   reconciliation.
7. Benchmark network location and connection reuse from candidate hosting
   environments.
8. Compare each stage against the baseline using median, p90, and p95 results.
9. Review trading-risk implications before enabling the optimized workflow in
   production.

Each implementation phase must include deterministic unit tests with mocked
clients. Cache expiry, refresh failure, symbol-not-found refresh, concurrent
retrieval failure, leverage invalidation, and entry-success/stop-failure paths
must be tested without real credentials or live trades.

## Acceptance Criteria

- Normal production logging and the latency exercise identify the exact
  handler-to-entry and notice-to-entry measurements.
- Timing allocation contains no unexplained nested double counting.
- Market-rule and leverage caches have bounded freshness and safe failure
  behavior.
- A newly listed or missing symbol triggers a refresh before rejection.
- All existing trading validations remain active.
- Trailing-stop placement and its failure remain observable.
- Repository unit, integration, and end-to-end checks pass.
- At least 20 representative DEMO samples show the optimized median, p90, and
  p95 against the recorded baseline.
- Production rollout remains subject to explicit review.

