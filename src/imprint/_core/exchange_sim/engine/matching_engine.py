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

import imprint._core.constant as c
from imprint._core.exchange_sim.engine.order_stream import compact_order_book
from imprint._core.exchange_sim.engine.user_data_stream import UserData
from imprint._core.utils.base import ExecutedOrdersArray, OrderBookArray


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

    slippage: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
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
    def init(self) -> None:
        UserData.init(self)

        cfgAC = self.manager.cfgAccount
        self.slippage[0] = cfgAC.slippage.fixed

    @override
    def reset(self) -> None:
        UserData.reset(self)

        self.matching_engine.order_book = self.order_book
        self.matching_engine.executed_orders = self.executed_orders


spec = [
    ("order_book", types.Array(nb.int64, 2, "C")),
    ("order_id_buf", types.MemoryView(nb.int64, 1, "C")),
    ("obRow", types.MemoryView(nb.int64, 1, "C")),
    ("executed_orders", types.Array(nb.int64, 2, "C")),
    ("eoRow", types.MemoryView(nb.int64, 1, "C")),
    ("slippage", types.MemoryView(nb.int64, 1, "C")),
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitMatchingEngine:
    """JIT-compiled high-performance order matching engine for simulated exchange execution."""

    def __init__(
        self,
        order_book: OrderBookArray,
        order_id_buf: memoryview,
        obRow: memoryview,
        executed_orders: ExecutedOrdersArray,
        eoRow: memoryview,
        slippage: memoryview,
    ) -> None:
        self.order_book: OrderBookArray = order_book
        self.order_id_buf: memoryview = order_id_buf
        self.obRow: memoryview = obRow
        self.executed_orders: ExecutedOrdersArray = executed_orders
        self.eoRow: memoryview = eoRow
        self.slippage: memoryview = slippage

    def matching(self, trade_timestamp: int, trade_nPrice: int) -> bool:
        """Process incoming trade ticks against active order book entries.

        Iterates through active order rows, evaluating execution or cancellation
        conditions against current trade timestamp and price, and compacts the book.

        Returns
        -------
        bool
            True if any client order was executed or modified during matching, otherwise False.
        """
        client_in_priority: bool = False
        for row in range(self.obRow[0]):
            order_timestamp: int64 = self.order_book[row, c.OB_timestamp]
            order_param: int64 = self.order_book[row, c.OB_orderParam]
            order_client_id: int64 = self.order_book[row, c.OB_clientOrderID]

            executed: bool = False
            if (trade_timestamp >= order_timestamp) and (
                (
                    bool(order_param & c.OF_NEW)
                    and self._processing_new_order(
                        trade_timestamp=trade_timestamp,
                        trade_nPrice=trade_nPrice,
                        order_nPrice=self.order_book[row, c.OB_nPrice],
                        order_param=order_param,
                        order_nQty=self.order_book[row, c.OB_nQty],
                        order_id=self.order_id_buf[0],
                        order_client_id=order_client_id,
                    )
                )
                or (
                    bool(order_param & c.OF_CANCEL)
                    and self._processing_cancel_order(
                        trade_timestamp=trade_timestamp,
                        order_id=self.order_id_buf[0],
                        order_client_id=order_client_id,
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
        order_nPrice: int64,
        order_param: int64,
        order_nQty: int64,
        order_id: int,
        order_client_id: int64,
    ) -> bool:
        """Evaluate and execute new market, limit, or stop trigger orders.

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
            order_client_id
        )
        self.executed_orders[self.eoRow[0], c.TP_nPrice] = nPrice
        self.executed_orders[self.eoRow[0], c.TP_nQty] = order_nQty
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
        slipageTicks = nPrice * self.slippage[0] // 10_000
        return nPrice + (slipageTicks if is_buy else -slipageTicks)

    def _processing_cancel_order(
        self, trade_timestamp: int, order_id: int, order_client_id: int64
    ) -> bool:
        """Cancel an existing active order matching the client order ID and log cancellation.

        Returns
        -------
        bool
            True if the order was found and canceled, otherwise False.
        """
        for row in range(self.obRow[0]):
            if self.order_book[row, c.OB_clientOrderID] == order_client_id:
                order_param: int64 = self.order_book[row, c.OB_orderParam]
                nPrice: int64 = self.order_book[row, c.OB_nPrice]
                nQty: int64 = self.order_book[row, c.OB_nQty]

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
                    order_client_id
                )
                self.executed_orders[self.eoRow[0], c.TP_nPrice] = nPrice
                self.executed_orders[self.eoRow[0], c.TP_nQty] = nQty
                self.executed_orders[self.eoRow[0], c.TP_nCommission] = 0
                self.executed_orders[self.eoRow[0], c.TP_nMAE] = 0
                self.executed_orders[self.eoRow[0], c.TP_nMFE] = 0
                self.eoRow[0] += 1
                return True

        return False
