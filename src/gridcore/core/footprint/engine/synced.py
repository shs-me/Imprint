import time
from abc import ABC, abstractmethod
from typing import override

from numpy import int64

from ... import constant as c
from ...ipc import NodeManager
from .reader import Reader


class Sync(ABC):
    def __init__(self, manager: NodeManager) -> None:
        self.manager = manager

        cfgMetrics = manager.cfgMetrics
        self.time_start_reading: memoryview = cfgMetrics.time_start_reading.cast("q")

        cfgRM = manager.cfgRiskManagment
        self.safe_lag: int = cfgRM.pass_signal_if_analysis_time_big

        cfgSN = manager.cfgSignal
        self.sn_cell_amount: int = cfgSN.cell_amount
        self.sn_safe_lag: int = cfgSN.safe_lag
        self.sn_data_size: int = cfgSN.data_size // 8
        self.sn_data: memoryview = cfgSN.data.cast("q")
        self.sn_wid: memoryview = cfgSN.writer_id.cast("q")
        self.sn_rid: memoryview = cfgSN.reader_id.cast("q")

        self._signal_id = 0
        self._count_send_signal: int = 0

    @property
    def signal_id(self) -> int:
        self._signal_id += 1
        return self._signal_id

    def send_signal(
        self,
        nPrice: int,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        is_market: bool,
        pass_lag: bool,
    ) -> None | int:
        if not pass_lag:
            if not self.lag_is_safe():
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

    def lag_is_safe(self) -> bool:
        lag: int = (time.perf_counter_ns() - self.time_start_reading[0]) // 1_000
        return True if (lag < self.safe_lag) else False


class Synced(Reader, ABC):
    def __init__(
        self,
        manager: NodeManager,
        sync: Sync,
        find_patterns_in_update_clusters: bool = False,
        find_patterns_in_update_closed_bar: bool = False,
        find_patterns_in_update_bar: bool = False,
    ) -> None:
        super().__init__(manager)

        self._sync: Sync = sync
        self.__fpiu_clusters: bool = find_patterns_in_update_clusters
        self.__fpiu_closed_bar: bool = find_patterns_in_update_closed_bar
        self.__fpiu_bar: bool = find_patterns_in_update_bar

        self._tick_by_tick_analyze: bool = (
            True if (self.__fpiu_bar or self.__fpiu_clusters) else False
        )

    @override
    def _update_clusters(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None:
        super()._update_clusters(idYmin, idYmax, idXmin, idXmax)
        if self.__fpiu_clusters:
            self.find_patterns_in_update_clusters(idYmin, idYmax, idXmin, idXmax)

    @override
    def _update_bar(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        super()._update_bar(idYmin, idYmax, idxBid, idxAsk)
        if self.__fpiu_bar:
            self.find_patterns_in_update_bar(idYmin, idYmax, idxBid, idxAsk)

    @override
    def _update_closed_bar_and_fp(self) -> None:
        super()._update_closed_bar_and_fp()
        if self.__fpiu_closed_bar:
            self.find_patterns_in_update_closed_bar()

    @abstractmethod
    def find_patterns_in_update_clusters(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None:
        pass

    @abstractmethod
    def find_patterns_in_update_closed_bar(self) -> None:
        pass

    @abstractmethod
    def find_patterns_in_update_bar(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        pass

    def send_signal(
        self,
        is_market: bool,
        is_long: bool,
        is_buy: bool,
        idy: int64,
        idx: int | None = None,
        pass_lag: bool = True,
    ) -> int | None:
        nPrice = int(self.con.to_nPrice(idy))
        idx = idx if (idx is not None) else self.last_idx
        timestamp = int(self.fp.bar[idx].ind.time.last_trade)
        return self._sync.send_signal(
            nPrice=nPrice,
            timestamp=timestamp,
            is_long=is_long,
            is_buy=is_buy,
            is_market=is_market,
            pass_lag=pass_lag,
        )
