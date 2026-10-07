from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import override

import numba as nb
from numba import (
    types,  # pyright: ignore[reportPrivateImportUsage]
)
from numba.experimental import (
    jitclass,  # pyright: ignore[reportUnknownVariableType, reportPrivateImportUsage]
)
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.exchange_sim.engine.order_stream import compact_order_book
from imprint._core.exchange_sim.engine.user_data_stream import UserData


@dataclass(slots=True)
class MatchingEngine(UserData, ABC):
    """Executes order matching, slippage calculation, and position book updates.

    Attributes
    ----------
    slippage : int
        Fixed slippage parameter in basis points retrieved from account configuration.
    matching_engine : JitMatchingEngine
        JIT-compiled high-performance matching engine instance.
    """

    slippage: int = field(init=False)

    matching_engine: JitMatchingEngine = field(init=False)

    @override
    def __post_init__(self) -> None:
        UserData.__post_init__(self)

        self.matching_engine = JitMatchingEngine(
            order_book=self.order_book,
            order_id_buf=self.order_id,
            obRow=self.obRow,
            executed_orders=self.executed_orders,
            eoRow=self.eoRow,
            slippage=self.slippage,
        )

    @override
    def post_init(self) -> None:
        UserData.post_init(self)

        cfgAC = self.manager.cfgAccount
        self.slippage = cfgAC.slippage.fixed

        self.matching_engine.slippage = self.slippage


spec = [
    ("order_book", types.Array(nb.int64, 2, "C")),
    ("order_id_buf", types.MemoryView(nb.int64, 1, "C")),
    ("obRow", types.MemoryView(nb.int64, 1, "C")),
    ("executed_orders", types.Array(nb.int64, 2, "C")),
    ("eoRow", types.MemoryView(nb.int64, 1, "C")),
    ("slippage", nb.int64),
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitMatchingEngine:
    """JIT-compiled high-performance order matching engine for simulated exchange execution.

    Parameters
    ----------
    order_book : ndarray of shape (N, M)
        C-contiguous order book buffer containing active order records.
    order_id_buf : memoryview of shape (1,)
        Monotonically increasing sequence buffer for generated order IDs.
    obRow : memoryview of shape (1,)
        Active row count pointer for the order book.
    executed_orders : ndarray of shape (K, P)
        C-contiguous execution log buffer for filled or canceled orders.
    eoRow : memoryview of shape (1,)
        Active row count pointer for the execution log.
    slippage : int
        Fixed slippage in basis points applied to market orders.

    Attributes
    ----------
    order_book : ndarray of shape (N, M)
        C-contiguous order book buffer containing active order records.
    order_id_buf : memoryview of shape (1,)
        Monotonically increasing sequence buffer for generated order IDs.
    obRow : memoryview of shape (1,)
        Active row count pointer for the order book.
    executed_orders : ndarray of shape (K, P)
        C-contiguous execution log buffer for filled or canceled orders.
    eoRow : memoryview of shape (1,)
        Active row count pointer for the execution log.
    slippage : int
        Fixed slippage in basis points applied to market orders.
    """

    def __init__(
        self,
        order_book: NDArray[int64],
        order_id_buf: memoryview,
        obRow: memoryview,
        executed_orders: NDArray[int64],
        eoRow: memoryview,
        slippage: int,
    ) -> None:
        self.order_book: NDArray[int64] = order_book
        self.order_id_buf: memoryview = order_id_buf
        self.obRow: memoryview = obRow
        self.executed_orders: NDArray[int64] = executed_orders
        self.eoRow: memoryview = eoRow
        self.slippage: int = slippage

    def matching(self, trade_timestamp: int, trade_nPrice: int) -> bool:
        """Process incoming trade ticks against active order book entries.

        Iterates through active order rows, evaluating execution or cancellation
        conditions against current trade timestamp and price, and compacts the book.

        Parameters
        ----------
        trade_timestamp : int
            Exchange timestamp of the incoming trade tick in nanoseconds or ticks.
        trade_nPrice : int
            Normalized price of the incoming trade tick.

        Returns
        -------
        bool
            True if any client order was executed or modified during matching, otherwise False.
        """
        client_in_priority: bool = False
        for row in range(self.obRow[0]):
            order_timestamp: int = self.order_book[row, c.OB_timestamp]
            order_param: int = self.order_book[row, c.OB_orderParam]
            client_order_id: int = self.order_book[row, c.OB_clientOrderID]

            executed: bool = False
            if (trade_timestamp >= order_timestamp) and (
                (
                    bool(order_param & c.OF_NEW)
                    and self._processing_new_order(
                        trade_timestamp=trade_timestamp,
                        trade_nPrice=trade_nPrice,
                        order_nPrice=self.order_book[row, c.OB_nPrice],
                        order_param=order_param,
                        nQty=self.order_book[row, c.OB_nQty],
                        order_id=self.order_id_buf[0],
                        client_order_id=client_order_id,
                    )
                )
                or (
                    bool(order_param & c.OF_CANCEL)
                    and self._processing_cancel_order(
                        trade_timestamp=trade_timestamp,
                        order_id=self.order_id_buf[0],
                        client_order_id=client_order_id,
                    )
                )
            ):
                self.order_book[row, c.OB_orderParam] &= ~(
                    c.OF_CANCEL | c.OF_NEW
                )
                self.order_book[row, c.OB_orderParam] |= (
                    c.OF_CANCELED | c.OF_FILLED
                )
                self.order_id_buf[0] += 1
                executed = True

            if executed:
                client_in_priority = True

        compact_order_book(self.obRow, self.order_book)
        return client_in_priority

    def _processing_new_order(
        self,
        trade_timestamp: int,
        trade_nPrice: int,
        order_nPrice: int,
        order_param: int,
        nQty: int,
        order_id: int,
        client_order_id: int,
    ) -> bool:
        """Evaluate and execute new market, limit, or stop trigger orders.

        Parameters
        ----------
        trade_timestamp : int
            Exchange timestamp of the trade tick.
        trade_nPrice : int
            Normalized price of the trade tick.
        order_nPrice : int
            Normalized limit price of the order.
        order_param : int
            Bitmask representing order type and flags.
        nQty : int
            Normalized order quantity.
        order_id : int
            Unique generated internal identifier for the execution record.
        client_order_id : int
            Client-assigned order identifier.

        Returns
        -------
        bool
            True if the order successfully met execution conditions and was logged, otherwise False.
        """
        is_buy: bool = bool(order_param & c.OF_BUY)

        if bool(order_param & c.OF_MARKET):
            nPrice = self._nPrice_with_slippage(trade_nPrice, is_buy)

        elif bool(order_param & c.OF_LIMIT) and (
            (is_buy and (trade_nPrice <= order_nPrice))
            or (not is_buy and (trade_nPrice >= order_nPrice))
        ):
            nPrice = order_nPrice

        elif bool(order_param & c.OF_MARKET_TRIGGER) and (
            (is_buy and (trade_nPrice >= order_nPrice))
            or (not is_buy and (trade_nPrice <= order_nPrice))
        ):
            order_param &= ~(c.OF_MARKET_TRIGGER)
            order_param |= c.OF_MARKET
            nPrice = self._nPrice_with_slippage(trade_nPrice, is_buy)

        else:
            return False

        order_param &= ~(c.OF_NEW)
        order_param |= c.OF_FILLED

        self.executed_orders[self.eoRow[0], c.TP_timestamp] = trade_timestamp
        self.executed_orders[self.eoRow[0], c.TP_order_param] = order_param
        self.executed_orders[self.eoRow[0], c.TP_order_id] = order_id
        self.executed_orders[self.eoRow[0], c.TP_client_order_id] = (
            client_order_id
        )
        self.executed_orders[self.eoRow[0], c.TP_nPrice] = nPrice
        self.executed_orders[self.eoRow[0], c.TP_nQty] = nQty
        self.executed_orders[self.eoRow[0], c.TP_nCommission] = 0
        self.executed_orders[self.eoRow[0], c.TP_nMAE] = 0
        self.executed_orders[self.eoRow[0], c.TP_nMFE] = 0
        self.eoRow[0] += 1
        return True

    def _nPrice_with_slippage(self, nPrice: int, is_buy: bool) -> int:
        """Calculate execution price adjusted for fixed slippage in basis points.

        Parameters
        ----------
        nPrice : int
            Base normalized price.
        is_buy : bool
            True if order is a buy order (slippage increases price), False for sell (decreases price).

        Returns
        -------
        int
            Slippage-adjusted normalized price.
        """
        slipageTicks = nPrice * self.slippage // 10_000
        return nPrice + (slipageTicks if is_buy else -slipageTicks)

    def _processing_cancel_order(
        self, trade_timestamp: int, order_id: int, client_order_id: int
    ) -> bool:
        """Cancel an existing active order matching the client order ID and log cancellation.

        Parameters
        ----------
        trade_timestamp : int
            Exchange timestamp when the cancellation is processed.
        order_id : int
            Unique generated internal identifier for the cancellation record.
        client_order_id : int
            Client-assigned order identifier to locate in the order book.

        Returns
        -------
        bool
            True if the order was found and canceled, otherwise False.
        """
        for row in range(self.obRow[0]):
            if self.order_book[row, c.OB_clientOrderID] == client_order_id:
                order_param: int = self.order_book[row, c.OB_orderParam]
                nPrice: int = self.order_book[row, c.OB_nPrice]
                nQty: int = self.order_book[row, c.OB_nQty]

                order_param &= ~(c.OF_NEW)
                order_param |= c.OF_CANCELED

                self.order_book[row, c.OB_orderParam] = order_param

                self.executed_orders[self.eoRow[0], c.TP_timestamp] = (
                    trade_timestamp
                )
                self.executed_orders[self.eoRow[0], c.TP_order_param] = (
                    order_param
                )
                self.executed_orders[self.eoRow[0], c.TP_order_id] = order_id
                self.executed_orders[self.eoRow[0], c.TP_client_order_id] = (
                    client_order_id
                )
                self.executed_orders[self.eoRow[0], c.TP_nPrice] = nPrice
                self.executed_orders[self.eoRow[0], c.TP_nQty] = nQty
                self.executed_orders[self.eoRow[0], c.TP_nCommission] = 0
                self.executed_orders[self.eoRow[0], c.TP_nMAE] = 0
                self.executed_orders[self.eoRow[0], c.TP_nMFE] = 0
                self.eoRow[0] += 1
                return True

        return False
