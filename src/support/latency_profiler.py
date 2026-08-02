from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Iterator


@dataclass(frozen=True, slots=True)
class LatencySpan:
    name: str
    duration_seconds: float
    task_name: str


class LatencyProfiler:
    """Collect monotonic wall-clock timings for one trigger-action invocation."""

    def __init__(self) -> None:
        self._started_at = perf_counter()
        self._spans: list[LatencySpan] = []

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        started_at = perf_counter()
        try:
            yield
        finally:
            task = asyncio.current_task()
            self._spans.append(
                LatencySpan(
                    name=name,
                    duration_seconds=perf_counter() - started_at,
                    task_name=task.get_name() if task is not None else "synchronous",
                )
            )

    @property
    def elapsed_seconds(self) -> float:
        return perf_counter() - self._started_at

    @property
    def spans(self) -> tuple[LatencySpan, ...]:
        return tuple(self._spans)

