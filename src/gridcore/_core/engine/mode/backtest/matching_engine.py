import time

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_data_prepper import BaseDataPrepper


class DataPrepper(BaseDataPrepper):
    def __init__(
        self, symbol: str, start_date: str, end_date: str, price_mult: int
    ) -> None:
        super().__init__(symbol, start_date, end_date)

        self.price_mult: int = price_mult

        self.dfm: NDArray[int64] = np.ndarray((100_000, 2), dtype=int64)
        self.dfmWid: memoryview = memoryview(bytearray(8)).cast("q")
        self.dfmRid: memoryview = memoryview(bytearray(8)).cast("q")
        self.max_row: int = self.dfm.shape[0]
        self.safe_lag: int = round(self.max_row * 0.1)

    def alarm_clock(self) -> None:
        while (
            (self.dfmWid[0] - self.dfmRid[0] + self.max_row) % self.max_row
        ) > self.safe_lag:
            time.sleep(0)

    def prepper_data(self, data: bytes) -> None:
        list_data: list[bytes] = data.split(b",")
        self.dfm[self.dfmWid[0], :] = (
            round(float(list_data[1]) * self.price_mult),
            int(list_data[5]),
        )
        new_row: int = self.dfmWid[0] + 1
        self.dfmWid[0] = new_row if (new_row <= self.max_row) else 0


class MatchingEngine:
    def __init__(self, manager: AgentManager) -> None:
        self.manager: AgentManager = manager

        cfgUS = manager.cfgUserStream
        self.cell_amount: int = cfgUS.cell_amount
        self.data: memoryview = cfgUS.data
        self.data_size: int = cfgUS.data_size
        self.data_header: memoryview = cfgUS.data_header.cast("q")
        self.writer_id: memoryview = cfgUS.writer_id.cast("q")
        self.reader_id: memoryview = cfgUS.reader_id.cast("q")

        self.prepper: DataPrepper
        self.trade_readed_time: memoryview = memoryview(bytearray(8)).cast("q")

    def _init_array(self) -> None:
        self.order_book: NDArray[int64]

    def matching(self, timestamp: int) -> None:
        _matching(
            timestamp=timestamp,
            order_book=self.order_book,
            dfm=self.prepper.dfm,
            dfmRid=self.prepper.dfmRid,
            dfmWid=self.prepper.dfmWid,
        )

    def set_user_data(self, data: bytes) -> None:
        cell: int = self.writer_id[0]
        start = cell * self.data_size
        self.data_header[cell] = len(data)
        self.data[start : start + len(data)] = data
        new_cell: int = cell + 1
        self.writer_id[0] = new_cell if (new_cell < self.cell_amount) else 0


@njit(cached=True)
def _matching(
    timestamp: int,
    order_book: NDArray[int64],
    dfm: NDArray[int64],
    dfmRid: memoryview,
    dfmWid: memoryview,
) -> None:
    pass


def processing_market_orders() -> None:
    pass


def processing_limit_orders() -> None:
    pass


def processing_cond_orders() -> None:
    pass
