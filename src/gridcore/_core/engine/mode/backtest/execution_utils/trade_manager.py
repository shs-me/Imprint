import numpy as np
from numpy import object_
from numpy.typing import NDArray

from ..... import constant as c
from ....base.utils.tm_con import TradeConverter

OPEN_ORDER: int = 0
TP_ORDER: int = 1
SL_ORDER: int = 2


class TradeManager:
    def __init__(self, converter: TradeConverter) -> None:
        self.con: TradeConverter = converter

        self.ohLines = self.con.cfgST.orders_history_rows
        self.ohCols = self.con.cfgST.orders_history_cols
        self.aoLines = self.con.cfgST.active_orders_rows
        self.aoCols = self.con.cfgST.active_orders_cols
        self._init_array()

    def _init_array(self) -> None:
        self.orders_history: NDArray[object_] = np.full(
            shape=(self.ohLines, self.ohCols), fill_value=None, dtype=object_
        )
        self.active_orders: NDArray[object_] = np.full(
            shape=(3, self.aoLines, self.aoCols), fill_value=None, dtype=object_
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
            if is_open:
                if _.longNqty > 0:
                    _.longEntryNprice = (
                        (_.longEntryNprice * _.longNqty) + (nPrice * nQty)
                    ) // (_.longNqty + nQty)
                else:
                    _.longEntryNprice = nPrice

                _.longNqty += nQty
            else:
                _.lockedNbalance = -(_.to_nMargin(_.longEntryNprice, nQty))
                _.nBalance = _.to_nPnl(nPrice, nQty, True)
                _.longNqty -= nQty

            if _.longNqty == 0:
                _.longEntryNprice = 0

        else:
            if is_open:
                if _.shortNqty > 0:
                    _.shortEntryNprice = (
                        (_.shortEntryNprice * _.shortNqty) + (nPrice * nQty)
                    ) // (_.shortNqty + nQty)
                else:
                    _.shortEntryNprice = nPrice

                _.shortNqty += nQty
            else:
                _.lockedNbalance = -(_.to_nMargin(_.shortEntryNprice, nQty))
                _.nBalance = _.to_nPnl(nPrice, nQty, False)
                _.shortNqty -= nQty

            if _.shortNqty == 0:
                _.shortEntryNprice = 0

        if (_.longNqty == 0) and (_.shortNqty == 0) and (self.aoWRow[0] == 1):
            if _.lockedNbalance > 0:
                _.lockedNbalance = -(_.lockedNbalance)

    def final_action(self) -> None:
        if self.con.cfgST.save_orders_history:
            np.save(
                c.ORDERS_HISTORY_DUMP_PATH, self.orders_history[: self.ohWRow[0], :]
            )
