import struct
from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint.core import constant as c
from imprint.core.exchange_sim.account import Account
from imprint.core.settings import StatusCodes as scs


@dataclass(slots=True)
class Order(Account, ABC):
    __order_book_row: int = field(init=False)

    __sus_cell_amount: int = field(init=False)
    __sus_data: memoryview = field(init=False)
    __sus_data_size: int = field(init=False)
    __sus_data_header: memoryview = field(init=False)
    __sus_wid: memoryview = field(init=False)
    __sus_rid: memoryview = field(init=False)

    executed_orders: NDArray[int64] = field(
        default_factory=lambda: np.zeros(
            (1000, c.TP_ConstantCount), dtype=np.int64
        ),
        init=False,
    )
    eoRow: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    order_book: NDArray[int64] = field(init=False)
    order_id: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    obRow: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    @override
    def __post_init__(self) -> None:
        Account.__post_init__(self)

        cfgAC = self.manager.cfgAccount
        self.__order_book_row = cfgAC.active_order_limit

        cfgSUS = self.manager.cfgSetUserStream
        self.__sus_cell_amount = cfgSUS.cell_amount
        self.__sus_data = cfgSUS.data.view
        self.__sus_data_size = cfgSUS.data_size
        self.__sus_data_header = cfgSUS.data_header.view
        self.__sus_wid = cfgSUS.writer_id.view.cast("q")
        self.__sus_rid = cfgSUS.reader_id.view.cast("q")

        self.executed_orders = np.zeros(
            (1000, c.TP_ConstantCount), dtype=np.int64
        )
        self.order_book = np.zeros(
            (self.__order_book_row, c.OB_ConstantCount), dtype=int64
        )

    @final
    @override
    def post_lock_balance(self) -> None:
        self.__update_order_book()

    @final
    def __update_order_book(self) -> None:
        timestamp, order_param, client_order_id, nPrice, nQty = (
            self.__get_user_data()
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

        self.executed_orders[self.eoRow[0], c.TP_timestamp] = timestamp
        self.executed_orders[self.eoRow[0], c.TP_order_param] = order_param
        self.executed_orders[self.eoRow[0], c.TP_order_id] = self.order_id[0]
        self.executed_orders[self.eoRow[0], c.TP_client_order_id] = (
            client_order_id
        )
        self.executed_orders[self.eoRow[0], c.TP_nPrice] = nPrice
        self.executed_orders[self.eoRow[0], c.TP_nQty] = nQty
        self.executed_orders[self.eoRow[0], c.TP_nCommission] = 0
        self.executed_orders[self.eoRow[0], c.TP_nMAE] = 0
        self.executed_orders[self.eoRow[0], c.TP_nMFE] = 0

        self.eoRow[0] += 1
        self.order_id[0] += 1

    @final
    def __get_user_data(self) -> tuple[int, int, int, int, int]:
        cell: int = self.__sus_rid[0]
        start: int = cell * self.__sus_data_size
        lrd = self.__sus_data_header[cell]

        raw_data = self.__sus_data[start : start + lrd]
        order_data = struct.unpack("@qqqqq", raw_data)

        new_cell: int = cell + 1
        self.__sus_rid[0] = (
            new_cell if (new_cell < self.__sus_cell_amount) else 0
        )
        return order_data


@njit(cache=True)
def compact_order_book(obRow: memoryview, ob: NDArray[int64]) -> None:
    row: int = 0
    while row < obRow[0]:
        if ob[row, c.OB_orderParam] & (c.OF_CANCELED | c.OF_FILLED):
            if (obRow[0] - 1) > row:
                ob[row : obRow[0] - 1, :] = ob[row + 1 : obRow[0], :]
                ob[obRow[0] - 1, :] = 0
            else:
                ob[row, :] = 0

            obRow[0] -= 1
        else:
            row += 1
