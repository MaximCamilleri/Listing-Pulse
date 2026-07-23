"""Binance USD-M Futures aggregate-trade data access."""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import TextIOWrapper
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen
from zipfile import ZipFile


REST_HISTORY_MS = 24 * 60 * 60 * 1000
REST_WINDOW_MS = 60 * 60 * 1000 - 1
DEFAULT_CACHE_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "binance"


@dataclass(frozen=True)
class Tick:
    """One Binance aggregate trade, ordered by exchange trade ID."""

    trade_id: int
    price: float
    quantity: float
    timestamp_ms: int


class BinanceTickFeed:
    """Read recent trades from REST and older trades from Binance archives."""

    def __init__(
        self,
        base_url: str = "https://fapi.binance.com",
        archive_url: str = "https://data.binance.vision",
        cache_directory: str | Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.archive_url = archive_url.rstrip("/")
        self.cache_directory = (
            Path(cache_directory) if cache_directory is not None else DEFAULT_CACHE_DIRECTORY
        )

    def iter_ticks(
        self,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
    ) -> Iterator[Tick]:
        """Yield aggregate trades in the inclusive time range."""
        if end_time_ms < start_time_ms:
            raise ValueError("end_time_ms must not be earlier than start_time_ms")

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if start_time_ms < now_ms - REST_HISTORY_MS:
            yield from self._iter_archive_ticks(symbol, start_time_ms, end_time_ms)
        else:
            yield from self._iter_rest_ticks(symbol, start_time_ms, end_time_ms)

    def _iter_rest_ticks(
        self, symbol: str, start_time_ms: int, end_time_ms: int
    ) -> Iterator[Tick]:
        window_start = start_time_ms
        last_trade_id: int | None = None

        while window_start <= end_time_ms:
            window_end = min(window_start + REST_WINDOW_MS, end_time_ms)
            next_trade_id: int | None = None

            while True:
                query: dict[str, str | int] = {"symbol": symbol, "limit": 1000}
                if next_trade_id is None:
                    query.update({"startTime": window_start, "endTime": window_end})
                else:
                    query["fromId"] = next_trade_id

                payload = self._get_json("/fapi/v1/aggTrades", query)
                if not payload:
                    break

                reached_window_end = False
                for item in payload:
                    tick = self._tick_from_mapping(item)
                    if tick.timestamp_ms > window_end:
                        reached_window_end = True
                        break
                    if last_trade_id is None or tick.trade_id > last_trade_id:
                        yield tick
                        last_trade_id = tick.trade_id

                if len(payload) < 1000 or reached_window_end:
                    break
                next_trade_id = int(payload[-1]["a"]) + 1

            window_start = window_end + 1

    def _iter_archive_ticks(
        self, symbol: str, start_time_ms: int, end_time_ms: int
    ) -> Iterator[Tick]:
        current_date = datetime.fromtimestamp(start_time_ms / 1000, timezone.utc).date()
        final_date = datetime.fromtimestamp(end_time_ms / 1000, timezone.utc).date()

        while current_date <= final_date:
            archive_path = self._download_daily_archive(symbol, current_date.isoformat())
            with ZipFile(archive_path) as archive:
                csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
                if not csv_names:
                    raise RuntimeError(f"no CSV file found in {archive_path}")
                with archive.open(csv_names[0]) as raw_file:
                    rows = csv.reader(TextIOWrapper(raw_file, encoding="utf-8"))
                    for row in rows:
                        try:
                            tick = Tick(
                                trade_id=int(row[0]),
                                price=float(row[1]),
                                quantity=float(row[2]),
                                timestamp_ms=int(row[5]),
                            )
                        except (ValueError, IndexError):
                            # Some archive files include a header row.
                            continue
                        if start_time_ms <= tick.timestamp_ms <= end_time_ms:
                            yield tick
            current_date += timedelta(days=1)

    def _download_daily_archive(self, symbol: str, date_text: str) -> Path:
        filename = f"{symbol}-aggTrades-{date_text}.zip"
        destination = self.cache_directory / symbol / filename
        if destination.exists():
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        url = (
            f"{self.archive_url}/data/futures/um/daily/aggTrades/"
            f"{symbol}/{filename}"
        )
        temporary = destination.with_suffix(".zip.part")
        try:
            with urlopen(url, timeout=60) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            temporary.replace(destination)
        except HTTPError as exc:
            temporary.unlink(missing_ok=True)
            if exc.code == 404:
                raise ValueError(
                    f"Binance has no archived aggregate trades for {symbol} on {date_text}"
                ) from exc
            raise
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return destination

    def _get_json(self, path: str, query: dict[str, str | int]):
        params = urlencode(query)
        with urlopen(f"{self.base_url}{path}?{params}", timeout=30) as response:
            return json.load(response)

    @staticmethod
    def _tick_from_mapping(item: dict) -> Tick:
        return Tick(
            trade_id=int(item["a"]),
            price=float(item["p"]),
            quantity=float(item["q"]),
            timestamp_ms=int(item["T"]),
        )
