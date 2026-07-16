import time
from abc import ABC

from ... import constant as c
from ...utils.monitoring.agent_manager import AgentManager


class Sync(ABC):
    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager

        cfgMetrics = manager.cfgMetrics
        self.time_start_reading: memoryview = cfgMetrics.time_start_reading.cast("q")

        cfgST = manager.cfgStrategy
        self.analysis_safe_lag_us: int = cfgST.analysis_safe_lag_microsecond
        self.cell_amount: int = cfgST.cell_amount
        self.readerId: int = cfgST.reader[1] // 8 - 1
        self.writerId: int = cfgST.writer[1] // 8 - 1
        self.nPriceId: int = cfgST.nPrice[1] // 8 - 1
        self.time_msId: int = cfgST.time_ms[1] // 8 - 1
        self.orderParamId: int = cfgST.orderParam[1] // 8 - 1
        self.signal_size: int = cfgST.signal_size // 8
        self.signal_offset: int = cfgST.offset // 8
        self.executeBuf: memoryview = manager.strategy_buf[
            slice(*cfgST.executeBuf)
        ].cast("q")

    def send_signal(
        self,
        nPrice: int,
        time_ms: int,
        is_long: bool,
        is_buy: bool,
        is_market: bool,
        pass_lag: bool,
    ) -> None:
        if not pass_lag:
            if not self.lag_is_safe():
                return

        orderParam = 0
        orderParam |= c.OF_LONG if is_long else c.OF_SHORT
        orderParam |= c.OF_BUY if is_buy else c.OF_SELL
        orderParam |= c.OF_MARKET if is_market else c.OF_LIMIT
        orderParam |= c.OF_NEW

        cell: int = self.executeBuf[self.writerId]
        start: int = cell * self.signal_size + self.signal_offset

        self.executeBuf[start + self.nPriceId] = nPrice
        self.executeBuf[start + self.time_msId] = time_ms
        self.executeBuf[start + self.orderParamId] = orderParam

        new_cell = cell + 1
        self.executeBuf[self.writerId] = new_cell if new_cell < self.cell_amount else 0

        self.sync_with_execution()

    def sync_with_execution(self) -> None:
        pass

    def lag_is_safe(self) -> bool:
        lag: int = (time.perf_counter_ns() - self.time_start_reading[0]) // 1_000
        return True if (lag < self.analysis_safe_lag_us) else False
