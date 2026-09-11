import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

from numpy import int64

from imprint._core import constant as c
from imprint._core.footprint.engine.reader import AlgorithmProtocol
from imprint._core.footprint.engine.reader import Reader as FootprintEngine
from imprint._core.footprint.models import Footprint
from imprint._core.ipc import NodeManager


@dataclass(slots=True)
class SyncWithExecution(ABC):
    manager: NodeManager

    time_start_reading: memoryview = field(init=False)
    safe_lag: int = field(init=False)
    sn_cell_amount: int = field(init=False)
    sn_safe_lag: int = field(init=False)
    sn_data_size: int = field(init=False)
    sn_data: memoryview = field(init=False)
    sn_wid: memoryview = field(init=False)
    sn_rid: memoryview = field(init=False)

    _signal_id: int = field(default=0, init=False)
    _count_send_signal: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        cfgMetrics = self.manager.cfgMetrics
        self.time_start_reading = cfgMetrics.time_start_reading.view.cast("q")

        cfgRM = self.manager.cfgRiskManagement
        self.safe_lag = cfgRM.pass_signal_if_analysis_time_big

        cfgSN = self.manager.cfgSignal
        self.sn_cell_amount = cfgSN.ring_buf.cell_amount
        self.sn_safe_lag = cfgSN.ring_buf.safe_lag
        self.sn_data_size = cfgSN.ring_buf.data_size // 8
        self.sn_data = cfgSN.ring_buf.data.view.cast("q")
        self.sn_wid = cfgSN.ring_buf.writer_id.view.cast("q")
        self.sn_rid = cfgSN.ring_buf.reader_id.view.cast("q")

    @property
    def signal_id(self) -> int:
        self._signal_id += 1
        return self._signal_id

    @final
    def send_signal(
        self,
        nPrice: int,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        is_market: bool,
        pass_lag: bool,
    ) -> None | int:
        if not pass_lag and (not self.lag_is_safe()):
            return

        if (
            (self.sn_wid[0] - self.sn_rid[0] + self.sn_cell_amount)
            % self.sn_cell_amount
        ) > self.sn_safe_lag:
            return

        orderParam = 0
        orderParam |= c.OF_LONG if is_long else c.OF_SHORT
        orderParam |= c.OF_BUY if is_buy else c.OF_SELL
        orderParam |= c.OF_MARKET if is_market else c.OF_LIMIT
        orderParam |= c.OF_NEW

        cell: int = self.sn_wid[0]
        start: int = cell * self.sn_data_size
        set_data: memoryview = self.sn_data[start : start + self.sn_data_size]
        set_data[0] = sid = self.signal_id
        set_data[1], set_data[2], set_data[3] = nPrice, timestamp, orderParam

        new_cell = cell + 1
        self.sn_wid[0] = new_cell if new_cell < self.sn_cell_amount else 0

        self.sync_with_execution()
        self._count_send_signal += 1
        return sid

    @abstractmethod
    def sync_with_execution(self) -> None:
        pass

    @final
    def lag_is_safe(self) -> bool:
        lag: int = (
            time.perf_counter_ns() - self.time_start_reading[0]
        ) // 1_000
        return lag < self.safe_lag


@dataclass
class Router(AlgorithmProtocol, ABC):
    _manager: NodeManager
    _sync: SyncWithExecution

    tick_by_tick_analyze: bool = field(default=True, init=False)

    is_backtest: bool = field(init=False)
    last_idx: memoryview = field(init=False)
    fp: Footprint = field(init=False)
    _engine: FootprintEngine = field(init=False)

    def __post_init__(self) -> None:
        self._engine = FootprintEngine(self._manager, self)
        self.is_backtest = self._manager.cfgSetup.backtesting
        self.last_idx = self._engine.last_idx.toreadonly()
        self.fp = self._engine.fp

    @abstractmethod
    @override
    def on_clusters_update(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None: ...

    @abstractmethod
    @override
    def on_bar_close(self) -> None: ...

    @abstractmethod
    @override
    def on_bar_update(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None: ...

    @final
    def send_signal(
        self,
        is_market: bool,
        is_long: bool,
        is_buy: bool,
        idy: int64,
        idx: int | None = None,
        pass_lag: bool = True,
    ) -> int | None:
        nPrice = int(self.fp.con.to_nPrice(idy))
        idx = idx if (idx is not None) else self.last_idx[0]
        timestamp = round(
            self.fp.bar[idx].ind.last_trade_time
            if self.is_backtest
            else time.time() * 1000
        )
        return self._sync.send_signal(
            nPrice=nPrice,
            timestamp=timestamp,
            is_long=is_long,
            is_buy=is_buy,
            is_market=is_market,
            pass_lag=pass_lag,
        )
