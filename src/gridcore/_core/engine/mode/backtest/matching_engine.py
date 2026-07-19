import time

import numpy as np
from numba import njit
from numpy import int64, uint8
from numpy.typing import NDArray

from .... import constant as c
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

        self._init_array()

    def _init_array(self) -> None:
        self.data_buf: NDArray[uint8] = np.frombuffer(self.data, uint8)
        self.order_book: NDArray[int64] = np.ndarray(
            (1000, c.OB_ConstantCount), dtype=int64
        )
        self.order_book.fill(0)
        self.obRow: memoryview = memoryview(bytearray(8)).cast("q")

    def update_order_book(
        self,
        timestamp: int,
        order_param: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        self.order_book[self.obRow[0], :] = timestamp, order_param, nPrice, nQty

    def matching(self, timestamp: int) -> None:
        _matching(
            timestamp=timestamp,
            order_book=self.order_book,
            obRow=self.obRow,
            dfm=self.prepper.dfm,
            dfmRid=self.prepper.dfmRid,
            dfmWid=self.prepper.dfmWid,
            data_buf=self.data_buf,
            data_buf_size=self.data_size,
            data_header=self.data_header,
            writer_id=self.writer_id,
            cell_amount=self.cell_amount,
        )


@njit(cached=True)
def _matching(
    timestamp: int,
    order_book: NDArray[int64],
    obRow: memoryview,
    dfm: NDArray[int64],
    dfmRid: memoryview,
    dfmWid: memoryview,
    data_buf: NDArray[uint8],
    data_buf_size: int,
    data_header: memoryview,
    writer_id: memoryview,
    cell_amount: int,
) -> None:
    pass


def processing_market_orders() -> None:
    pass


def processing_limit_orders() -> None:
    pass


def processing_cond_orders() -> None:
    pass


def set_user_data(
    data: bytes,
    data_buf: NDArray[uint8],
    data_buf_size: int,
    data_header: memoryview,
    writer_id: memoryview,
    cell_amount: int,
) -> None:
    cell: int = writer_id[0]
    start: int = cell * data_buf_size
    data_header[cell] = len(data)
    data_buf[start : start + len(data)] = data
    new_cell: int = cell + 1
    writer_id[0] = new_cell if (new_cell < cell_amount) else 0


def compact_order_book(order_row: int, obRow: memoryview, ob: NDArray[int64]) -> None:
    if (obRow[0] - 1) > order_row:
        ob[order_row : obRow[0] - 1, :] = ob[order_row + 1 : obRow[0], :]
        ob[obRow[0] - 1, :] = 0
