"""Own startup and shutdown of the configured event-to-trade workflow."""

import asyncio
import threading
from collections.abc import Sequence
from typing import get_args

from src.control.trade.binance_controller import BinanceController
from src.control.event_to_trade import EVENT_CHANNELS, TRADE_CHANNELS, EventToTrade
from src.support.logger import get_logger

logger = get_logger(__name__)


async def start_trader(
    stop_event: threading.Event | None = None,
    *,
    combinations: Sequence[tuple[EVENT_CHANNELS, TRADE_CHANNELS]] | None = None,
) -> None:
    """Run selected pairs together; any listener exit shuts down the group.

    For example, combinations=[("UPBIT", "BINANCE"), ("BITHUMB", "BINANCE")].
    Omitting combinations defaults to Upbit and Binance.
    """
    pairs = list(combinations) if combinations is not None else [("UPBIT", "BINANCE")]
    if not pairs:
        raise ValueError("At least one event/trade combination is required")
    seen = set()
    for pair in pairs:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("Each combination must contain an event source and trade source")
        event, trade = pair
        if event not in get_args(EVENT_CHANNELS) or trade not in get_args(TRADE_CHANNELS):
            raise ValueError(f"Unsupported event/trade combination: {pair!r}")
        if (event, trade) in seen:
            raise ValueError(f"Duplicate event/trade combination: {pair!r}")
        seen.add((event, trade))

    workflows: list[EventToTrade] = []
    trade_controls: dict[TRADE_CHANNELS, BinanceController] = {}
    telegram = None
    for event, trade in pairs:
        workflow = EventToTrade(event, trade, trade_control=trade_controls.get(trade), telegram=telegram)
        workflows.append(workflow)
        trade_controls[trade] = workflow.trade_control
        telegram = workflow.event_control.telegram
    await run_workflows(workflows, stop_event)


async def run_workflows(
    workflows: Sequence[EventToTrade],
    stop_event: threading.Event | None = None,
) -> None:
    """Run assembled workflows, also used by the latency diagnostic."""
    if not workflows:
        raise ValueError("At least one workflow is required")
    stop_event = stop_event if stop_event is not None else threading.Event()
    trade_controls = {id(workflow.trade_control): workflow.trade_control for workflow in workflows}
    transports = {id(workflow.event_control.telegram): workflow.event_control.telegram for workflow in workflows}
    listener_tasks: list[asyncio.Task[None]] = []
    shutdown_task = None
    failed = False
    try:
        for controller in trade_controls.values():
            await controller.start()
        for workflow in workflows:
            await workflow.event_control.start()
        # All subscriptions must exist before readiness and update dispatch begin.
        for index, transport in enumerate(transports.values()):
            listener_tasks.append(asyncio.create_task(
                transport.run_forever(), name=f"telegram-connection-{index}",
            ))
        shutdown_task = asyncio.create_task(
            _wait_for_shutdown(stop_event), name="shutdown-waiter"
        )
        done, _ = await asyncio.wait(
            (*listener_tasks, shutdown_task), return_when=asyncio.FIRST_COMPLETED
        )
        if shutdown_task in done:
            logger.info("Application shutdown requested")
        for task in listener_tasks:
            if task in done:
                await task
    except BaseException:
        failed = True
        logger.exception("Event-to-trade application stopped")
        raise
    finally:
        stop_event.set()
        if shutdown_task is not None:
            shutdown_task.cancel()
        # Stop incoming updates once, then drain every queue before closing Binance.
        results = await asyncio.gather(
            *(transport.stop() for transport in transports.values()),
            return_exceptions=True,
        )
        tasks = [*listener_tasks]
        if shutdown_task is not None:
            tasks.append(shutdown_task)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        results.extend(await asyncio.gather(
            *(workflow.event_control.stop() for workflow in workflows),
            return_exceptions=True,
        ))
        results.extend(await asyncio.gather(
            *(controller.stop() for controller in trade_controls.values()),
            return_exceptions=True,
        ))
        errors = [result for result in results if isinstance(result, BaseException)]
        for error in errors:
            logger.error("Workflow cleanup failed: %s", error, exc_info=error)
        if errors and not failed:
            raise errors[0]


async def _wait_for_shutdown(stop_event: threading.Event) -> None:
    """Bridge the process-safe shutdown flag into the asyncio lifecycle."""
    while not stop_event.is_set():
        await asyncio.sleep(0.1)
