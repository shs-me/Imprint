import time
from abc import ABC, abstractmethod

from ... import constant as c
from ...ipc import NodeManager


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
        return self.signal_id

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
        ) > self.safe_lag:
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
