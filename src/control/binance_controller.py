import asyncio
from contextlib import asynccontextmanager
from decimal import Decimal, ROUND_DOWN
import time

from binance_sdk_derivatives_trading_usds_futures.rest_api.models import (
    NewAlgoOrderResponse,
    NewOrderResponse,
)

from src.config.settings import settings
from src.integration.binance_integration import (
    BinanceIntegration,
    BinanceLeverageBracket,
    BinanceMarketRules,
)
from src.support.binance_price_cache import BinancePriceCache
from src.support.latency_profiler import LatencyProfiler
from src.support.logger import get_logger

logger = get_logger(__name__)


class BinanceController:
    def __init__(
        self,
        quote_amount: Decimal | None = None,
        binance_client: BinanceIntegration | None = None,
        price_cache: BinancePriceCache | None = None,
    ) -> None:
        self.binance_client = binance_client or BinanceIntegration()
        self.quote_amount = Decimal(
            str(settings.order_quote_amount if quote_amount is None else quote_amount)
        )
        if self.quote_amount <= 0:
            raise ValueError("quote_amount must be positive")

        self.price_cache = price_cache or BinancePriceCache()
        self.market_rules: dict[str, BinanceMarketRules] = {}
        self.leverage_brackets: dict[str, list[BinanceLeverageBracket]] = {}
        self.confirmed_leverage: dict[str, int] = {}
        self._leverage_confirmed_at: dict[str, float] = {}
        self._metadata_refreshed_at: float | None = None
        self._condition = asyncio.Condition()
        self._active_trades = 0
        self._maintenance_active = False
        self._waiting_trades = 0
        self._leverage_locks: dict[str, asyncio.Lock] = {}
        self._stop_event = asyncio.Event()
        self._maintenance_task: asyncio.Task | None = None
        self._started = False
        logger.debug("BinanceController initialized")

    async def start(self) -> None:
        if self._started:
            return
        if not settings.trading_enabled:
            logger.info("Binance runtime initialization skipped: trading is disabled")
            return
        self._started = True
        self._stop_event.clear()
        try:
            await self.binance_client.start_price_stream(self.price_cache.update_message)
            await self.maintain_trading_env()
            self._maintenance_task = asyncio.create_task(
                self._create(), name="binance-environment-maintenance"
            )
        except BaseException:
            self._started = False
            await self.binance_client.stop_price_stream()
            raise

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._stop_event.set()
        task, self._maintenance_task = self._maintenance_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self.binance_client.stop_price_stream()

    async def _create(self) -> None:
        """Periodically refresh pre-trade metadata without competing with trades."""
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=settings.binance_env_refresh_interval_seconds,
                )
            except asyncio.TimeoutError:
                try:
                    await self.maintain_trading_env()
                except Exception:
                    logger.exception(
                        "Periodic Binance trading-environment refresh failed"
                    )

    async def place_market_order(
        self,
        symbol: str,
        direction: str,
        callback_rate: Decimal,
        latency_profiler: LatencyProfiler | None = None,
    ) -> tuple[NewOrderResponse, NewAlgoOrderResponse] | None:
        if not settings.trading_enabled:
            logger.error(
                "Failed to place trade on symbol=%s because trading is disabled",
                symbol,
            )
            return None

        symbol = symbol.upper().strip()
        if not symbol:
            raise ValueError("symbol must not be empty.")
        direction = direction.upper().strip()
        if direction not in {"BUY", "SELL"}:
            raise ValueError(
                f'Direction must be "BUY" or "SELL". "{direction}" is not supported.'
            )
        callback_rate = Decimal(str(callback_rate))
        if not Decimal("0.1") <= callback_rate <= Decimal("10"):
            raise ValueError("callback_rate must be between 0.1 and 10 percent.")

        await self._ensure_symbol_metadata(symbol)
        async with self._trade_access():
            rules = self._require_rules(symbol)
            live_price = self.price_cache.require(
                symbol, settings.binance_price_max_age_seconds
            )
            quantity = self._calculate_quantity(rules, live_price.price)
            notional = quantity * live_price.price
            leverage = self._get_max_leverage(
                symbol, self.leverage_brackets[symbol], notional
            )
            await self._confirm_leverage(symbol, leverage)

            logger.info(
                "Placing Binance market entry order symbol=%s direction=%s "
                "quote_amount=%s price=%s quantity=%s leverage=%s callback_rate=%s",
                symbol,
                direction,
                self.quote_amount,
                live_price.price,
                quantity,
                leverage,
                callback_rate,
            )
            if latency_profiler is None:
                try:
                    entry = await self.binance_client.place_market_order(
                        symbol=symbol, side=direction, quantity=quantity
                    )
                except Exception:
                    self._invalidate_leverage(symbol)
                    raise
            else:
                with latency_profiler.span(f"{symbol}.binance.market_entry"):
                    try:
                        entry = await self.binance_client.place_market_order(
                            symbol=symbol, side=direction, quantity=quantity
                        )
                    except Exception:
                        self._invalidate_leverage(symbol)
                        raise

            executed_quantity = Decimal(str(entry.executed_qty))
            if executed_quantity <= 0:
                raise RuntimeError(f"Entry was not filled: {entry}")
            stop_side = "SELL" if direction == "BUY" else "BUY"
            if latency_profiler is None:
                trailing_stop = await self.binance_client.place_trailing_stop_order(
                    symbol=symbol,
                    side=stop_side,
                    quantity=executed_quantity,
                    callback_rate=callback_rate,
                )
            else:
                with latency_profiler.span(f"{symbol}.binance.trailing_stop"):
                    trailing_stop = await self.binance_client.place_trailing_stop_order(
                        symbol=symbol,
                        side=stop_side,
                        quantity=executed_quantity,
                        callback_rate=callback_rate,
                    )
            return entry, trailing_stop

    async def maintain_trading_env(self) -> None:
        async with self._maintenance_access():
            rules, brackets = await asyncio.gather(
                self.binance_client.get_market_rules(),
                self.binance_client.get_leverage_brackets(),
            )
            if not rules or not brackets:
                raise RuntimeError("Binance returned incomplete trading metadata")
            self.market_rules = dict(rules)
            self.leverage_brackets = dict(brackets)
            self._metadata_refreshed_at = time.monotonic()
            logger.info(
                "Refreshed Binance trading environment rules=%s brackets=%s",
                len(rules),
                len(brackets),
            )

    async def _ensure_symbol_metadata(self, symbol: str) -> None:
        fresh = (
            self._metadata_refreshed_at is not None
            and time.monotonic() - self._metadata_refreshed_at
            <= settings.binance_env_max_age_seconds
        )
        if fresh and symbol in self.market_rules and symbol in self.leverage_brackets:
            return
        await self.maintain_trading_env()
        if symbol not in self.market_rules or symbol not in self.leverage_brackets:
            raise ValueError(f"Binance futures symbol is unavailable: {symbol}")

    def _require_rules(self, symbol: str) -> BinanceMarketRules:
        rules = self.market_rules[symbol]
        if rules.status != "TRADING":
            raise ValueError(f"Binance futures symbol is not trading: {symbol}")
        if rules.step_size <= 0:
            raise ValueError(f"Binance returned invalid step size for {symbol}")
        return rules

    def _calculate_quantity(
        self, rules: BinanceMarketRules, price: Decimal
    ) -> Decimal:
        quantity = (
            (self.quote_amount / price / rules.step_size).to_integral_value(
                rounding=ROUND_DOWN
            )
            * rules.step_size
        )
        if quantity < rules.min_quantity:
            raise ValueError(
                f"Calculated quantity is below the minimum for {rules.symbol}"
            )
        if quantity > rules.max_quantity:
            quantity = rules.max_quantity
        if quantity * price < rules.min_notional:
            raise ValueError(
                f"Calculated notional is below the minimum for {rules.symbol}"
            )
        return quantity

    def _get_max_leverage(
        self,
        symbol: str,
        leverage_brackets: list[BinanceLeverageBracket],
        notional_value: Decimal,
    ) -> int:
        matching = next(
            (
                bracket
                for bracket in sorted(
                    leverage_brackets, key=lambda item: item.notional_floor
                )
                if bracket.notional_floor <= notional_value < bracket.notional_cap
            ),
            None,
        )
        if matching is None:
            raise ValueError(
                f"No Binance leverage bracket supports notional "
                f"{notional_value} for {symbol}"
            )
        return matching.initial_leverage

    async def _confirm_leverage(self, symbol: str, leverage: int) -> None:
        lock = self._leverage_locks.setdefault(symbol, asyncio.Lock())
        async with lock:
            confirmed_at = self._leverage_confirmed_at.get(symbol)
            confirmation_is_fresh = (
                confirmed_at is not None
                and time.monotonic() - confirmed_at
                <= settings.binance_leverage_reconcile_seconds
            )
            if (
                self.confirmed_leverage.get(symbol) == leverage
                and confirmation_is_fresh
            ):
                return
            await self.binance_client.set_initial_leverage(symbol, leverage)
            self.confirmed_leverage[symbol] = leverage
            self._leverage_confirmed_at[symbol] = time.monotonic()

    def _invalidate_leverage(self, symbol: str) -> None:
        self.confirmed_leverage.pop(symbol, None)
        self._leverage_confirmed_at.pop(symbol, None)

    @asynccontextmanager
    async def _trade_access(self):
        async with self._condition:
            self._waiting_trades += 1
            try:
                await self._condition.wait_for(
                    lambda: not self._maintenance_active
                )
                self._active_trades += 1
            finally:
                self._waiting_trades -= 1
        try:
            yield
        finally:
            async with self._condition:
                self._active_trades -= 1
                self._condition.notify_all()

    @asynccontextmanager
    async def _maintenance_access(self):
        async with self._condition:
            await self._condition.wait_for(
                lambda: self._active_trades == 0
                and not self._maintenance_active
                and self._waiting_trades == 0
            )
            self._maintenance_active = True
        try:
            yield
        finally:
            async with self._condition:
                self._maintenance_active = False
                self._condition.notify_all()
