import struct
import time
from dataclasses import dataclass, field
from typing import final, override

import numpy as np
from numba import njit
from numpy import bool_, int64, uint8
from numpy.typing import NDArray

from .. import constant as c
from ..ipc import NodeManager
from ..pipeline.utils.base_data_prepper import BaseDataPrepper
from ..settings import StatusCodes as scs


@dataclass(slots=True)
class DataPrepper(BaseDataPrepper):
    price_mult: int

    dfm: NDArray[int64] = field(init=False)
    dfmWid: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    dfmRid: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    max_row: int = field(init=False)
    safe_lag: int = field(init=False)

    @override
    def __post_init__(self) -> None:
        DataPrepper.__post_init__(self)

        self.dfm = np.ndarray((100_000, 2), dtype=int64)
        self.max_row = self.dfm.shape[0]
        self.safe_lag = round(self.max_row * 0.9)

    @override
    def alarm_clock(self) -> None:
        while (
            (self.dfmWid[0] - self.dfmRid[0] + self.max_row) % self.max_row
        ) > self.safe_lag:
            time.sleep(0)

    @override
    def prepper_data(self, line: NDArray[int64]) -> None:
        self.dfm[self.dfmWid[0], :] = line[0], line[2]
        new_row: int = self.dfmWid[0] + 1
        self.dfmWid[0] = new_row if (new_row < self.max_row) else 0

    @override
    def post_prepper(self) -> None:
        pass


@dataclass
class MatchingEngine:
    manager: NodeManager

    slippage: int = field(init=False)
    order_book_row: int = field(init=False)

    gus_cell_amount: int = field(init=False)
    gus_data: memoryview = field(init=False)
    gus_data_size: int = field(init=False)
    gus_data_header: memoryview = field(init=False)
    gus_wid: memoryview = field(init=False)
    gus_rid: memoryview = field(init=False)

    sus_cell_amount: int = field(init=False)
    sus_data: memoryview = field(init=False)
    sus_data_size: int = field(init=False)
    sus_data_header: memoryview = field(init=False)
    sus_wid: memoryview = field(init=False)
    sus_rid: memoryview = field(init=False)

    trade_readed_time: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    order_id: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    data_buf: NDArray[uint8] = field(init=False)
    data_example: NDArray[int64] = field(init=False)
    deRow: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    order_book: NDArray[int64] = field(init=False)
    obRow: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    prepper: DataPrepper = field(init=False)

    def __post_init__(self) -> None:
        cfgAC = self.manager.cfgAccount
        self.slippage = cfgAC.slippage.int_
        self.order_book_row = cfgAC.active_order_limit

        cfgGUS = self.manager.cfgGetUserStream
        self.gus_cell_amount = cfgGUS.cell_amount
        self.gus_data = cfgGUS.data.view
        self.gus_data_size = cfgGUS.data_size
        self.gus_data_header = cfgGUS.data_header.view
        self.gus_wid = cfgGUS.writer_id.view.cast("q")
        self.gus_rid = cfgGUS.reader_id.view.cast("q")

        cfgSUS = self.manager.cfgSetUserStream
        self.sus_cell_amount = cfgSUS.cell_amount
        self.sus_data = cfgSUS.data.view
        self.sus_data_size = cfgSUS.data_size
        self.sus_data_header = cfgSUS.data_header.view
        self.sus_wid = cfgSUS.writer_id.view.cast("q")
        self.sus_rid = cfgSUS.reader_id.view.cast("q")

        self.trade_readed_time = memoryview(bytearray(8)).cast("q")
        self.order_id = memoryview(bytearray(8)).cast("q")

        self._init_array()

        self.prepper = DataPrepper(
            symbol=self.manager.cfgCoin.symbol,
            start_date=self.manager.cfgSetup.backtest_start_date,
            end_date=self.manager.cfgSetup.backtest_end_date,
            price_mult=self.manager.cfgCoin.price_mult,
        )
        self.prepper.start()

    def _init_array(self) -> None:
        """Initializes NumPy wrappers over shared user stream buffer, order book, and event logs."""

        self.data_buf = np.frombuffer(self.gus_data, uint8)
        self.data_buf.fill(0)
        self.data_example = np.zeros((1000, c.TP_ConstantCount), dtype=int64)
        self.order_book = np.zeros(
            (self.order_book_row, c.OB_ConstantCount), dtype=int64
        )

    @final
    def _update_order_book(self) -> None:
        """Appends pending order to simulated order book array."""
        raw_data = self._get_user_data()
        timestamp, order_param, client_order_id, nPrice, nQty = struct.unpack(
            "@qqqqq", raw_data
        )

        if self.obRow[0] >= self.order_book.shape[0]:
            self.manager.set_proc_sc(scs.ORDER_LIMIT, wait_main_task=True)
            return

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
            0,
            0,
        )
        self.order_id[0] += 1
        self.deRow[0] += 1

    @final
    def _get_user_data(self) -> memoryview:
        cell: int = self.sus_rid[0]
        start: int = cell * self.sus_data_size
        lrd = self.sus_data_header[cell]
        raw_data = self.sus_data[start : start + lrd]
        new_cell: int = cell + 1
        self.sus_rid[0] = new_cell if (new_cell < self.sus_cell_amount) else 0
        return raw_data


@njit(cache=True)
def matching(
    trade_timestamp: int,
    trade_nPrice: int,
    order_book: NDArray[int64],
    order_id_buf: memoryview,
    obRow: memoryview,
    data_example: NDArray[int64],
    deRow: memoryview,
    slippage: int,
) -> bool:
    """Numba JIT kernel matching active limit, market, and trigger orders against incoming tick price."""

    client_in_priority: bool = False
    order_row: int = 0
    while order_row < obRow[0]:
        order_timestamp: int = order_book[order_row, c.OB_timestamp]
        order_param: int = order_book[order_row, c.OB_orderParam]
        client_order_id: int = order_book[order_row, c.OB_clientOrderID]
        order_nPrice: int = order_book[order_row, c.OB_nPrice]
        order_nQty: int = order_book[order_row, c.OB_nQty]

        data = None
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
                0,
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
) -> tuple[int, int, int, int, int, int, int, int] | None:
    """Numba JIT kernel evaluating individual order fill conditions, slippage, and OCO cancellations."""

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
        mask: NDArray[bool_] = (
            order_book[: obRow[0], c.OB_clientOrderID] == client_order_id
        )
        order_book[: obRow[0], c.OB_orderParam][mask] &= ~(c.OF_NEW)
        order_book[: obRow[0], c.OB_orderParam][mask] |= c.OF_CANCELED

    order_param &= ~(c.OF_NEW | c.OF_CANCELED)
    order_param |= c.OF_FILLED

    return trade_timestamp, order_param, order_id, nPrice, nQty, 0, 0, 0


@njit(cache=True)
def _nPrice_with_slippage(
    nPrice: int,
    is_buy: bool,
    slippage: int,
) -> int:
    """Numba JIT kernel applying configured slippage deviation to execution price."""

    slipageTicks = nPrice * slippage // 10_000
    return nPrice + (slipageTicks if is_buy else -slipageTicks)


@njit(cache=True)
def _compact_order_book(
    order_row: int,
    obRow: memoryview,
    ob: NDArray[int64],
) -> None:
    """Numba JIT kernel removing filled or canceled order from active order book array."""

    if (obRow[0] - 1) > order_row:
        ob[order_row : obRow[0] - 1, :] = ob[order_row + 1 : obRow[0], :]
        ob[obRow[0] - 1, :] = 0
    else:
        ob[order_row, :] = 0

    obRow[0] -= 1


@njit(cache=True)
def set_user_data(
    data: NDArray[uint8],
    data_buf: NDArray[uint8],
    data_buf_size: int,
    data_header: memoryview,
    writer_id: memoryview,
    cell_amount: int,
) -> None:
    """Numba JIT kernel writing execution event payload into UserStream ring buffer."""

    cell: int = writer_id[0]
    start: int = cell * data_buf_size
    data_header[cell] = len(data)
    data_buf[start : start + len(data)] = data
    new_cell: int = cell + 1
    writer_id[0] = new_cell if (new_cell < cell_amount) else 0
