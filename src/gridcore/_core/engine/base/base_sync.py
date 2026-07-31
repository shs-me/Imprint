"""Signal transmission helper synchronizing Logic and Execution engines."""

import time
from abc import ABC

from ... import constant as c
from ...utils.monitoring.agent_manager import AgentManager


class Sync(ABC):
    """Base class packing strategy signals into Signal ring buffer.

    Attributes:
        safe_lag (int): Maximum processing lag threshold in microseconds.
    """

    def __init__(self, manager: AgentManager) -> None:
        """Binds metrics buffers and Signal ring buffer memory views."""

        self.manager = manager

        cfgMetrics = manager.cfgMetrics
        self.time_start_reading: memoryview = cfgMetrics.time_start_reading.cast("q")

        cfgRM = manager.cfgRiskManagment
        self.safe_lag: int = cfgRM.pass_signal_if_analysis_time_big

        cfgSN = manager.cfgSignal
        self.cell_amount: int = cfgSN.cell_amount
        self.data_size: int = cfgSN.data_size // 8
        self.data: memoryview = cfgSN.data.cast("q")
        self.writer_id: memoryview = cfgSN.writer_id.cast("q")
        self.reader_id: memoryview = cfgSN.reader_id.cast("q")

        self._count_send_signal: int = 0

    def send_signal(
        self,
        nPrice: int,
        time_ms: int,
        is_long: bool,
        is_buy: bool,
        is_market: bool,
        pass_lag: bool,
    ) -> None:
        """Packs trade signal attributes into Signal ring buffer cell and notifies Execution process.

        Args:
            nPrice (int): Fixed-point limit or trigger target price.
            time_ms (int): Signal creation timestamp in milliseconds.
            is_long (bool): True for Long position, False for Short.
            is_buy (bool): True for Buy order, False for Sell.
            is_market (bool): True for Market execution, False for Limit.
            pass_lag (bool): Flag to force signal dispatch despite processing latency.
        """

        if not pass_lag:
            if not self.lag_is_safe():
                return

        orderParam = 0
        orderParam |= c.OF_LONG if is_long else c.OF_SHORT
        orderParam |= c.OF_BUY if is_buy else c.OF_SELL
        orderParam |= c.OF_MARKET if is_market else c.OF_LIMIT
        orderParam |= c.OF_NEW

        cell: int = self.writer_id[0]
        start: int = cell * self.data_size
        set_data: memoryview = self.data[start : start + self.data_size]
        set_data[0], set_data[1], set_data[2] = nPrice, time_ms, orderParam

        new_cell = cell + 1
        self.writer_id[0] = new_cell if new_cell < self.cell_amount else 0

        self.sync_with_execution()
        self._count_send_signal += 1

    def sync_with_execution(self) -> None:
        """Hook for waking Execution process event waiters upon signal dispatch."""

        pass

    def lag_is_safe(self) -> bool:
        """Checks if current strategy processing latency is within safe threshold bounds.

        Returns:
            bool: True if lag is acceptable.
        """

        lag: int = (time.perf_counter_ns() - self.time_start_reading[0]) // 1_000
        return True if (lag < self.safe_lag) else False
