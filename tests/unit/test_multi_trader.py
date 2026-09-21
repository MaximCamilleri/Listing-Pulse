import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.interface.trade_interface import start_trader


PAIRS = [("UPBIT", "BINANCE"), ("BITHUMB", "BINANCE")]


class MultiTraderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stop_event = threading.Event()
        self.both_running = asyncio.Event()
        self.running = set()
        self.stopped = set()
        self.listeners = []
        self.trader = AsyncMock()

        async def stop_trader():
            self.assertEqual(self.stopped, {"UPBIT", "BITHUMB"})

        self.trader.stop.side_effect = stop_trader

    def compose(self, event, trade, *, trade_control, telegram):
        listener = AsyncMock()
        stopped = asyncio.Event()

        async def run():
            self.trader.start.assert_awaited_once()
            self.running.add(event)
            if len(self.running) == 2:
                self.both_running.set()
            await stopped.wait()

        async def stop():
            self.stopped.add(event)
            stopped.set()

        listener.telegram.run_forever.side_effect = run
        listener.stop.side_effect = stop
        self.listeners.append(listener)
        return SimpleNamespace(
            event_source=event, trade_source=trade, event_control=listener,
            trade_control=trade_control if trade_control is not None else self.trader,
        )

    async def test_listeners_run_concurrently_and_share_one_trader(self):
        with patch("src.interface.trade_interface.EventToTrade", side_effect=self.compose) as compose:
            task = asyncio.create_task(start_trader(self.stop_event, combinations=PAIRS))
            try:
                await asyncio.wait_for(self.both_running.wait(), 1)
                self.stop_event.set()
                await asyncio.wait_for(task, 1)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self.assertIs(compose.call_args_list[1].kwargs["trade_control"], self.trader)
            self.trader.start.assert_awaited_once()
            self.trader.stop.assert_awaited_once()
            for listener in self.listeners:
                listener.stop.assert_awaited_once()

    async def test_listener_failure_stops_peer_and_propagates(self):
        def compose(*args, **kwargs):
            workflow = self.compose(*args, **kwargs)
            if workflow.event_source == "UPBIT":
                async def fail():
                    await asyncio.sleep(0)
                    raise RuntimeError("listener failed")
                workflow.event_control.telegram.run_forever.side_effect = fail
            return workflow

        with patch("src.interface.trade_interface.EventToTrade", side_effect=compose):
            with self.assertLogs("src.interface.trade_interface", level="ERROR"):
                with self.assertRaisesRegex(RuntimeError, "listener failed"):
                    await asyncio.wait_for(start_trader(combinations=PAIRS), 1)
        self.trader.stop.assert_awaited_once()
        self.assertEqual(self.stopped, {"UPBIT", "BITHUMB"})

    async def test_cancellation_cleans_up_all_workflows(self):
        with patch("src.interface.trade_interface.EventToTrade", side_effect=self.compose):
            task = asyncio.create_task(start_trader(combinations=PAIRS))
            try:
                await asyncio.wait_for(self.both_running.wait(), 1)
            finally:
                with self.assertLogs("src.interface.trade_interface", level="ERROR"):
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
        self.trader.stop.assert_awaited_once()

    async def test_startup_failure_stops_all_constructed_workflows(self):
        self.trader.start.side_effect = RuntimeError("startup failed")
        with patch("src.interface.trade_interface.EventToTrade", side_effect=self.compose):
            with self.assertLogs("src.interface.trade_interface", level="ERROR"):
                with self.assertRaisesRegex(RuntimeError, "startup failed"):
                    await start_trader(combinations=PAIRS)
        for listener in self.listeners:
            listener.telegram.run_forever.assert_not_awaited()
        self.trader.stop.assert_awaited_once()

    async def test_cleanup_failure_still_stops_other_listener_and_trader(self):
        def compose(*args, **kwargs):
            workflow = self.compose(*args, **kwargs)
            if workflow.event_source == "UPBIT":
                workflow.event_control.telegram.run_forever.side_effect = None
                async def fail_stop():
                    self.stopped.add("UPBIT")
                    raise RuntimeError("stop failed")
                workflow.event_control.stop.side_effect = fail_stop
            return workflow

        with patch("src.interface.trade_interface.EventToTrade", side_effect=compose):
            with self.assertLogs("src.interface.trade_interface", level="ERROR"):
                with self.assertRaisesRegex(RuntimeError, "stop failed"):
                    await asyncio.wait_for(start_trader(combinations=PAIRS), 1)
        self.trader.stop.assert_awaited_once()

    async def test_invalid_combinations_fail_before_construction(self):
        with patch("src.interface.trade_interface.EventToTrade") as compose:
            for pairs in ([], [PAIRS[0], PAIRS[0]], [("UNKNOWN", "BINANCE")], [("UPBIT", "")], ["UPBIT"]):
                with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                    await start_trader(combinations=pairs)
            compose.assert_not_called()
