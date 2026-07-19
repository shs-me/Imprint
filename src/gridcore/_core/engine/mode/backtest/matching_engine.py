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
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        price_mult: int,
        is_complete: memoryview,
    ) -> None:
        super().__init__(symbol, start_date, end_date)

        self.price_mult: int = price_mult
        self.is_complete: memoryview = is_complete

        self.dfm: NDArray[int64] = np.ndarray((100_000, 2), dtype=int64)
        self.dfmWid: memoryview = memoryview(bytearray(8)).cast("q")
        self.dfmRid: memoryview = memoryview(bytearray(8)).cast("q")
        self.max_row: int = self.dfm.shape[0]
        self.safe_lag: int = round(self.max_row * 0.9)

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
        self.dfmWid[0] = new_row if (new_row < self.max_row) else 0

    def post_prepper(self) -> None:
        self.is_complete[0] = 1


class MatchingEngine:
    def __init__(self, manager: AgentManager) -> None:
        self.manager: AgentManager = manager

        cfgAC = manager.cfgAccount
        self.slippage: int = cfgAC.slipage

        cfgUS = manager.cfgUserStream
        self.cell_amount: int = cfgUS.cell_amount
        self.data: memoryview = cfgUS.data
        self.data_size: int = cfgUS.data_size
        self.data_header: memoryview = cfgUS.data_header.cast("q")
        self.writer_id: memoryview = cfgUS.writer_id.cast("q")
        self.reader_id: memoryview = cfgUS.reader_id.cast("q")

        self.trade_readed_time: memoryview = memoryview(bytearray(8)).cast("q")
        self.order_id: memoryview = memoryview(bytearray(8)).cast("q")

        self._init_array()

        cfgMetrics = manager.cfgMetrics
        self.price_prec: memoryview = cfgMetrics.price_precision.cast("q")
        self.dfm_complete: memoryview = cfgMetrics.dfm_comlpete

        self.prepper: DataPrepper = DataPrepper(
            symbol=manager.symbol,
            start_date=manager.cfgBacktesting.backtest_start_date,
            end_date=manager.cfgBacktesting.backtest_end_date,
            price_mult=10 ** self.price_prec[0],
            is_complete=self.dfm_complete,
        )
        self.prepper.start()

    def _init_array(self) -> None:
        self.data_buf: NDArray[uint8] = np.frombuffer(self.data, uint8)
        self.data_example: NDArray[int64] = np.array([0, 0, 0, 0, 0], dtype=int64)
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
        self.obRow[0] += 1

    def matching(self, timestamp: int) -> None:
        while True:
            if _matching(
                timestamp=timestamp,
                time_readed_trade=self.trade_readed_time,
                order_book=self.order_book,
                obRow=self.obRow,
                dfm=self.prepper.dfm,
                dfmRid=self.prepper.dfmRid,
                dfmWid=self.prepper.dfmWid,
                data_buf=self.data_buf,
                data_example=self.data_example,
                data_buf_size=self.data_size,
                data_header=self.data_header,
                writer_id=self.writer_id,
                order_id=self.order_id,
                cell_amount=self.cell_amount,
                slippage=self.slippage,
            ):
                break
            else:
                if self.prepper.error is not None:
                    raise RuntimeError(self.prepper.error)
                else:
                    while self.prepper.dfmWid[0] == self.prepper.dfmRid[0]:
                        if self.dfm_complete[0] == 0:
                            time.sleep(0)
                        else:
                            return


@njit(cache=True, nogil=True)
def _matching(
    timestamp: int,
    time_readed_trade: memoryview,
    order_book: NDArray[int64],
    obRow: memoryview,
    dfm: NDArray[int64],
    dfmRid: memoryview,
    dfmWid: memoryview,
    data_buf: NDArray[uint8],
    data_example: NDArray[int64],
    data_buf_size: int,
    data_header: memoryview,
    writer_id: memoryview,
    order_id: memoryview,
    cell_amount: int,
    slippage: int,
) -> bool:
    max_row: int = dfm.shape[0]
    while time_readed_trade[0] < timestamp:
        row: int = dfmRid[0]

        if row == dfmWid[0]:
            return False

        new_row: int = row + 1
        dfmRid[0] = new_row if (new_row < max_row) else 0

        time_readed_trade[0] = dfm[row, 1]

        if obRow[0] == 0:
            continue

        trade_nPrice: int = dfm[row, 0]
        trade_timestamp: int = dfm[row, 1]

        order_row = 0
        while order_row < obRow[0]:
            order_timestamp: int = order_book[order_row, c.OB_timestamp]
            order_param: int = order_book[order_row, c.OB_orderParam]
            order_nPrice: int = order_book[order_row, c.OB_nPrice]
            order_nQty: int = order_book[order_row, c.OB_nQty]

            if trade_timestamp >= order_timestamp:
                data = processing_order(
                    trade_timestamp,
                    order_param,
                    order_id,
                    trade_nPrice,
                    order_nPrice,
                    order_nQty,
                    slippage,
                    data_example,
                )
            else:
                data = None

            if data is not None:
                set_user_data(
                    data=data,
                    data_buf=data_buf,
                    data_buf_size=data_buf_size,
                    data_header=data_header,
                    writer_id=writer_id,
                    cell_amount=cell_amount,
                )
                compact_order_book(order_row, obRow, order_book)
            else:
                order_row += 1

    return True


@njit(cache=True)
def processing_order(
    trade_timestamp: int,
    order_param: int,
    order_id: memoryview,
    trade_nPrice: int,
    order_nPrice: int,
    order_nQty: int,
    slippage: int,
    data_example: NDArray[int64],
) -> NDArray[uint8] | None:
    is_buy: bool = bool(order_param & c.OF_BUY)

    executed_nPrice = trade_nPrice
    if bool(order_param & c.OF_MARKET):
        executed_nPrice = nPrice_with_slippage(trade_nPrice, is_buy, slippage)

    elif bool(order_param & c.OF_LIMIT) and (
        (is_buy and (trade_nPrice <= order_nPrice))
        or (not is_buy and (trade_nPrice >= order_nPrice))
    ):
        pass

    elif bool(order_param & c.OF_MARKET_TRIGER) and (
        (is_buy and (trade_nPrice >= order_nPrice))
        or (not is_buy and (trade_nPrice <= order_nPrice))
    ):
        order_param &= ~(c.OF_MARKET_TRIGER)
        order_param |= c.OF_MARKET
        executed_nPrice = nPrice_with_slippage(trade_nPrice, is_buy, slippage)

    else:
        return

    order_param &= ~(c.OF_NEW)
    order_param |= c.OF_FILLED

    data_example[:] = (
        trade_timestamp,
        order_param,
        order_id[0],
        executed_nPrice,
        order_nQty,
    )
    return data_example.view(uint8)


@njit(cache=True)
def nPrice_with_slippage(nPrice: int, is_buy: bool, slipage: int) -> int:
    slipageTicks = nPrice * slipage // 10_000
    return nPrice + (slipageTicks if is_buy else -slipageTicks)


@njit(cache=True)
def set_user_data(
    data: NDArray[uint8],
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


@njit(cache=True)
def compact_order_book(order_row: int, obRow: memoryview, ob: NDArray[int64]) -> None:
    if (obRow[0] - 1) > order_row:
        ob[order_row : obRow[0] - 1, :] = ob[order_row + 1 : obRow[0], :]
        ob[obRow[0] - 1, :] = 0
    else:
        ob[order_row, :] = 0

    obRow[0] -= 1
