from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.exchange_sim.account import Account
from imprint._core.settings import StatusCodes as scs


@dataclass(slots=True)
class Order(Account, ABC):
    """Represent an active order stream manager handling internal order books and execution logs.

    Attributes
    ----------
    executed_orders : ndarray of shape (1000, TP_ConstantCount)
        Ring buffer or log storing executed order entries.
    eoRow : memoryview of shape (1,), dtype=q
        Current write head index within ``executed_orders``.
    order_book : ndarray of shape (active_order_limit, OB_ConstantCount)
        Active order book ledger.
    order_id : memoryview of shape (1,), dtype=q
        Monotonically increasing integer identifier assigned to successive orders.
    obRow : memoryview of shape (1,), dtype=q
        Current write head / row cursor within ``order_book``.
    """

    executed_orders: NDArray[int64] = field(
        default_factory=lambda: np.zeros((0, 0), dtype=np.int64), init=False
    )
    eoRow: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    order_book: NDArray[int64] = field(
        default_factory=lambda: np.zeros((0, 0), dtype=int64), init=False
    )
    order_id: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    obRow: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    @override
    def init(self) -> None:
        Account.init(self)

        limit = self.manager.cfgAccount.active_order_limit

        if limit != self.order_book.shape[0]:
            self.order_book = np.zeros((limit, c.OB_ConstantCount), dtype=int64)
        else:
            self.order_book.fill(0)

        if limit != self.executed_orders.shape[0]:
            self.executed_orders = np.zeros(
                (limit, c.TP_ConstantCount), dtype=int64
            )
        else:
            self.executed_orders.fill(0)

    @override
    def reset(self) -> None:
        Account.reset(self)

        self.eoRow[0], self.obRow[0], self.order_id[0] = 0, 0, 0

    @final
    @override
    def post_lock_balance(self) -> None:
        """Process balance locks and synchronize the internal order book."""
        self.__update_order_book()

    @final
    def __update_order_book(self) -> None:
        """Pull order data from the ring buffer and append it to the order book and execution logs."""
        timestamp, order_param, client_order_id, nPrice, nQty = (
            self.manager.cfgOrderStream.ring_buf.get_data()
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


@njit(cache=True)
def compact_order_book(obRow: memoryview, ob: NDArray[int64]) -> None:
    """Compact the order book in-place by removing canceled or filled orders.

    Parameters
    ----------
    obRow : memoryview of shape (1,), dtype=q
        Mutable scalar memoryview containing the current active row count of the order book.
        Decremented in-place as rows are compacted.
    ob : ndarray of shape (N, OB_ConstantCount)
        Active order book matrix to be compacted in-place.
    """
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
