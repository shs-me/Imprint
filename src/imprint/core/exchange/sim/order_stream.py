import struct
from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from ...settings import StatusCodes as scs
from ..account import AccountManager


@dataclass(slots=True)
class Order(AccountManager, ABC):
    __order_book_row: int = field(init=False)

    __sus_cell_amount: int = field(init=False)
    __sus_data: memoryview = field(init=False)
    __sus_data_size: int = field(init=False)
    __sus_data_header: memoryview = field(init=False)
    __sus_wid: memoryview = field(init=False)
    __sus_rid: memoryview = field(init=False)

    data_example: NDArray[int64] = field(init=False)
    deRow: memoryview = field(
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
        AccountManager.__post_init__(self)

        cfgAC = self.manager.cfgAccount
        self.__order_book_row = cfgAC.active_order_limit

        cfgSUS = self.manager.cfgSetUserStream
        self.__sus_cell_amount = cfgSUS.cell_amount
        self.__sus_data = cfgSUS.data.view
        self.__sus_data_size = cfgSUS.data_size
        self.__sus_data_header = cfgSUS.data_header.view
        self.__sus_wid = cfgSUS.writer_id.view.cast("q")
        self.__sus_rid = cfgSUS.reader_id.view.cast("q")

        self.data_example = np.zeros((1000, c.TP_ConstantCount), dtype=np.int64)
        self.order_book = np.zeros(
            (self.__order_book_row, c.OB_ConstantCount), dtype=int64
        )

    @final
    @override
    def post_update_lockedNbalance(self) -> None:
        self.__update_order_book()

    @final
    def __update_order_book(self) -> None:
        raw_data = self.__get_user_data()
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
    def __get_user_data(self) -> memoryview:
        cell: int = self.__sus_rid[0]
        start: int = cell * self.__sus_data_size
        lrd = self.__sus_data_header[cell]
        raw_data = self.__sus_data[start : start + lrd]
        new_cell: int = cell + 1
        self.__sus_rid[0] = new_cell if (new_cell < self.__sus_cell_amount) else 0
        return raw_data


@njit(cache=True)
def compact_order_book(order_row: int, obRow: memoryview, ob: NDArray[int64]) -> None:
    if (obRow[0] - 1) > order_row:
        ob[order_row : obRow[0] - 1, :] = ob[order_row + 1 : obRow[0], :]
        ob[obRow[0] - 1, :] = 0
    else:
        ob[order_row, :] = 0

    obRow[0] -= 1
