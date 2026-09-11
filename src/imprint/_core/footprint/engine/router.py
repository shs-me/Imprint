import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

from numpy import int64

from imprint._core import constant as c
from imprint._core.configs import SignalStream
from imprint._core.footprint.engine.reader import AlgorithmProtocol
from imprint._core.footprint.engine.reader import Reader as FootprintEngine
from imprint._core.footprint.models import Footprint
from imprint._core.ipc import NodeManager


@dataclass(slots=True)
class SyncWithExecution(ABC):
    manager: NodeManager

    time_start_reading: memoryview = field(init=False)
    safe_lag: int = field(init=False)
    __ss: SignalStream = field(init=False)
    _signal_id: int = field(default=0, init=False)
    _count_send_signal: int = field(default=0, init=False)

    @final
    def __post_init__(self) -> None:
        cfgMetrics = self.manager.cfgMetrics
        self.time_start_reading = cfgMetrics.time_start_reading.view.cast("q")

        cfgRM = self.manager.cfgRiskManagement
        self.safe_lag = cfgRM.pass_signal_if_analysis_time_big

        self.__ss = self.manager.cfgSignalStream

    @final
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
        s = self.__ss.ring_buf
        if not pass_lag and (not self.lag_is_safe()):
            return

        if s.lag_not_is_safe():
            return

        order_param = 0
        order_param |= c.OF_LONG if is_long else c.OF_SHORT
        order_param |= c.OF_BUY if is_buy else c.OF_SELL
        order_param |= c.OF_MARKET if is_market else c.OF_LIMIT
        order_param |= c.OF_NEW

        s.set_data(self.signal_id, nPrice, timestamp, order_param)
        self.sync_with_execution()
        self._count_send_signal += 1
        return self._signal_id

    @abstractmethod
    def sync_with_execution(self) -> None: ...

    @final
    def lag_is_safe(self) -> bool:
        lag: int = (
            time.perf_counter_ns() - self.time_start_reading[0]
        ) // 1_000
        return lag < self.safe_lag


@dataclass(slots=True)
class Router(AlgorithmProtocol, ABC):
    _manager: NodeManager
    _sync: SyncWithExecution

    tick_by_tick_analyze: bool = field(default=True, init=False)

    is_backtest: bool = field(init=False)
    last_idx: memoryview = field(init=False)
    fp: Footprint = field(init=False)
    _engine: FootprintEngine = field(init=False)

    @final
    def __post_init__(self) -> None:
        self._engine = FootprintEngine(self._manager, self)
        self.is_backtest = self._manager.cfgSetup.backtesting
        self.last_idx = self._engine.last_idx.toreadonly()
        self.fp = self._engine.fp

        self.post_init()

    def post_init(self) -> None: ...

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
