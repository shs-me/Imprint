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
    ) -> None:
        super().__init__(symbol, start_date, end_date)

        self.price_mult: int = price_mult

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
        pass


class MatchingEngine:
    def __init__(self, manager: AgentManager) -> None:
        self.manager: AgentManager = manager

        cfgAC = manager.cfgAccount
        self.slippage: int = cfgAC.slippage

        cfgUS = manager.cfgUserStream
        self.cell_amount: int = cfgUS.cell_amount
        self.data: memoryview = cfgUS.data
        self.data_buf_size: int = cfgUS.data_size
        self.data_header: memoryview = cfgUS.data_header.cast("q")
        self.writer_id: memoryview = cfgUS.writer_id.cast("q")
        self.reader_id: memoryview = cfgUS.reader_id.cast("q")

        self.trade_readed_time: memoryview = memoryview(bytearray(8)).cast("q")
        self.order_id: memoryview = memoryview(bytearray(8)).cast("q")

        self._init_array()

        self.prepper: DataPrepper = DataPrepper(
            symbol=manager.cfgCoin.symbol,
            start_date=manager.cfgSetup.backtest_start_date,
            end_date=manager.cfgSetup.backtest_end_date,
            price_mult=manager.cfgCoin.price_mult,
        )
        self.prepper.start()

    def _init_array(self) -> None:
        self.data_buf: NDArray[uint8] = np.frombuffer(self.data, uint8)
        self.data_example: NDArray[int64] = np.ndarray((1000, 6), dtype=int64)
        self.deRow: memoryview = memoryview(bytearray(8)).cast("q")

        self.order_book: NDArray[int64] = np.ndarray(
            (1000, c.OB_ConstantCount), dtype=int64
        )
        self.order_book.fill(0)
        self.obRow: memoryview = memoryview(bytearray(8)).cast("q")

    def _update_order_book(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        self.order_book[self.obRow[0], c.OB_timestamp] = timestamp
        self.order_book[self.obRow[0], c.OB_orderParam] = order_param
        self.order_book[self.obRow[0], c.OB_clientOrderID] = client_order_id
        self.order_book[self.obRow[0], c.OB_nPrice] = nPrice
        self.order_book[self.obRow[0], c.OB_nQty] = nQty
        self.obRow[0] += 1

        self.data_example[self.deRow[0], :] = (
            timestamp,
            order_param,
            self.order_id[0],
            nPrice,
            nQty,
            0,
        )
        self.order_id[0] += 1
        self.deRow[0] += 1


@njit(cache=True)
def _matching(
    trade_timestamp: int,
    trade_nPrice: int,
    order_book: NDArray[int64],
    order_id_buf: memoryview,
    obRow: memoryview,
    data_example: NDArray[int64],
    deRow: memoryview,
    slippage: int,
) -> bool:
    client_in_priority: bool = False
    order_row: int = 0
    while order_row < obRow[0]:
        order_timestamp: int = order_book[order_row, c.OB_timestamp]
        order_param: int = order_book[order_row, c.OB_orderParam]
        client_order_id: int = order_book[order_row, c.OB_clientOrderID]
        order_nPrice: int = order_book[order_row, c.OB_nPrice]
        order_nQty: int = order_book[order_row, c.OB_nQty]

        data = None
        date_ = None
        if bool(order_param & c.OF_NEW):
            if trade_timestamp >= order_timestamp:
                data_ = _processing_order(
                    trade_timestamp,
                    trade_nPrice,
                    order_nPrice,
                    order_param,
                    order_nQty,
                    client_order_id,
                    order_book,
                    obRow,
                    order_id_buf[0],
                    slippage,
                )
                if data_ is not None:
                    data_example[deRow[0], :] = data_
                    data = data_example[deRow[0], :]
                    deRow[0] += 1
                    order_id_buf[0] += 1

        elif bool(order_param & c.OF_CANCELED):
            data_example[deRow[0], :] = (
                trade_timestamp,
                order_param,
                order_id_buf[0],
                order_nPrice,
                order_nQty,
                0,
            )

            data = data_example[deRow[0], :]
            order_id_buf[0] += 1
            deRow[0] += 1

        if data is not None:
            _compact_order_book(order_row, obRow, order_book)
            client_in_priority = True
        else:
            order_row += 1

    return client_in_priority


@njit(cache=True)
def _processing_order(
    trade_timestamp: int,
    trade_nPrice: int,
    order_nPrice: int,
    order_param: int,
    nQty: int,
    client_order_id: int,
    order_book: NDArray[int64],
    obRow: memoryview,
    order_id: int,
    slippage: int,
) -> tuple[int, int, int, int, int, int] | None:
    is_buy: bool = bool(order_param & c.OF_BUY)

    nPrice = trade_nPrice
    if bool(order_param & c.OF_MARKET):
        nPrice = _nPrice_with_slippage(trade_nPrice, is_buy, slippage)

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
        nPrice = _nPrice_with_slippage(trade_nPrice, is_buy, slippage)

    else:
        return

    if bool(order_param & c.OF_OCO):
        mask = order_book[: obRow[0], c.OB_clientOrderID] == client_order_id
        order_book[: obRow[0], c.OB_orderParam][mask] &= ~(c.OF_NEW)
        order_book[: obRow[0], c.OB_orderParam][mask] |= c.OF_CANCELED

    order_param &= ~(c.OF_NEW | c.OF_CANCELED)
    order_param |= c.OF_FILLED

    return trade_timestamp, order_param, order_id, nPrice, nQty, 0


@njit(cache=True)
def _nPrice_with_slippage(
    nPrice: int,
    is_buy: bool,
    slippage: int,
) -> int:
    slipageTicks = nPrice * slippage // 10_000
    return nPrice + (slipageTicks if is_buy else -slipageTicks)


@njit(cache=True)
def _compact_order_book(
    order_row: int,
    obRow: memoryview,
    ob: NDArray[int64],
) -> None:
    if (obRow[0] - 1) > order_row:
        ob[order_row : obRow[0] - 1, :] = ob[order_row + 1 : obRow[0], :]
        ob[obRow[0] - 1, :] = 0
    else:
        ob[order_row, :] = 0

    obRow[0] -= 1


@njit(cache=True)
def _set_user_data(
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
