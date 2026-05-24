import numpy as np
from numpy import object_
from numpy.typing import NDArray

from core import constant as c
from core.engine.agents_utils.utils import TradeConverter

OPEN_ORDER: int = 0
TP_ORDER: int = 1
SL_ORDER: int = 2


class TradeManager:
    def __init__(self, converter: TradeConverter) -> None:
        self.con: TradeConverter = converter

        self.ohLines = self.con.cfgST.ordersHistoryLines
        self.ohCols = self.con.cfgST.ordersHistoryCols
        self.aoLines = self.con.cfgST.activeOrdersLines
        self.aoCols = self.con.cfgST.activeOrdersCols
        self._init_array()

    def _init_array(self) -> None:
        self.orders_history: NDArray[object_] = np.ndarray(
            shape=(self.ohLines, self.ohCols), dtype=object_
        )
        self.active_orders: NDArray[object_] = np.ndarray(
            shape=(3, self.aoLines, self.aoCols), dtype=object_
        )

        self.ohWRow: memoryview = memoryview(bytearray(8)).cast("q")
        self.aoWRow: memoryview = memoryview(bytearray(8)).cast("q")

    def update_orders_history(
        self,
        nPrice: int,
        nQty: int,
        timestamp: int,
        orderParam: int,
        orderID: int | None,
        nCommission: int = 0,
    ) -> None:
        ohWRow, oh, _ = self.ohWRow, self.orders_history, self.con
        # - - -
        order_param: list[int] = [nPrice, nQty, timestamp, orderParam, nCommission]
        order_param.append(orderID if (orderID is not None) else _.newOrderId)
        oh[ohWRow[0], :] = order_param
        ohWRow[0] += 1
        if ohWRow[0] >= oh.shape[0]:
            oldLines = oh.shape[0]
            self.orders_history = np.resize(
                oh, new_shape=((oldLines + self.ohLines), self.ohCols)
            )
            self.orders_history[oldLines:, :] = None

    def set_active_order(
        self,
        nPrice: int,
        nQty: int,
        timestamp: int,
        orderParam: int,
        orderID: int | None = None,
        openWrow: int | None = None,
        is_tp: bool = True,
    ) -> None:
        _, ao, aoWRow = self.con, self.active_orders, self.aoWRow
        # - - -
        order_param: list[int] = [nPrice, nQty, timestamp, orderParam]
        order_param.append(orderID if (orderID is not None) else _.newOrderId)
        if openWrow is None:
            ao[OPEN_ORDER, aoWRow[0], :] = order_param
            aoWRow[0] += 1
            if aoWRow[0] >= ao.shape[1]:
                oldLines = ao.shape[1]
                self.active_orders = np.resize(
                    ao, new_shape=(3, (oldLines + self.aoLines), self.aoCols)
                )
                self.active_orders[:, oldLines:, :] = None
        else:
            ao[(TP_ORDER if is_tp else SL_ORDER), openWrow, :] = order_param

        self.update_orders_history(nPrice, nQty, timestamp, orderParam, order_param[-1])

    def cancel_active_order(self, aoRow: int, timestamp: int, typeOrder: int) -> None:
        nPrice: int = self.active_orders[typeOrder, aoRow, c.AO_nPrice]
        nQty: int = self.active_orders[typeOrder, aoRow, c.AO_nQty]
        orderParam: int = self.active_orders[typeOrder, aoRow, c.AO_orderParam]
        orderParam &= ~(c.OF_NEW)
        orderParam |= c.OF_CANCELED
        self.update_orders_history(nPrice, nQty, timestamp, orderParam, None)
        self.active_orders[typeOrder, aoRow, :] = None

    def compact_active_orders(self, aoRow: int) -> None:
        ao, aoWRow = self.active_orders, self.aoWRow
        # - - -
        if (aoWRow[0] - 1) > aoRow:
            ao[:, aoRow : aoWRow[0] - 1, :] = ao[:, aoRow + 1 : aoWRow[0], :]
            ao[:, aoWRow[0] - 1, :] = None

    def updatePosition(
        self, nPrice: int, nQty: int, nCommission: int, is_open: bool, is_long: bool
    ) -> None:
        _ = self.con
        # - - -
        _.nBalance = -nCommission
        if is_long:
            _.longNqty += nQty if is_open else -nQty
            if is_open:
                _.longWeight += nQty
                _.longPweight += nPrice * nQty
                _.longEntryNprice = _.longPweight // _.longWeight
            else:
                _.lockedNbalance = -(_.to_nMargin(_.longEntryNprice, nQty))
                _.nBalance = _.to_nPnl(nPrice, nQty, True)

            if _.longNqty == 0:
                _.longWeight, _.longPweight, _.longEntryNprice = 0, 0, 0
        else:
            _.shortNqty += nQty if is_open else -nQty
            if is_open:
                _.shortWeight += nQty
                _.shortPweight += nPrice * nQty
                _.shortEntryNprice = _.shortPweight // _.shortWeight
            else:
                _.lockedNbalance = -(_.to_nMargin(_.shortEntryNprice, nQty))
                _.nBalance = _.to_nPnl(nPrice, nQty, False)

            if _.shortNqty == 0:
                _.shortWeight, _.shortPweight, _.shortEntryNprice = 0, 0, 0

    def final_action(self) -> None:
        if self.con.cfgST.saveOrdersHistory:
            np.save(
                c.ORDERS_HISTORY_DUMP_PATH, self.orders_history[: self.ohWRow[0], :]
            )
