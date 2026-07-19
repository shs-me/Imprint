import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ..... import constant as c
from .tm_con import TradeConverter


class TradeManager:
    def __init__(self, converter: TradeConverter) -> None:
        self.con: TradeConverter = converter

        self.oh_rows: int = 10_000
        self.oh_cols: int = c.TradeParam._ConstantCount

        self._init_array()

    def _init_array(self) -> None:
        self.orders_history: NDArray[int64] = np.full(
            shape=(self.oh_rows, self.oh_cols), fill_value=None, dtype=int64
        )
        self.ohWid: memoryview = memoryview(bytearray(8)).cast("q")

    def update_orders_history(
        self,
        timestamp: int,
        order_param: int,
        order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        ohWid, oh = self.ohWid, self.orders_history
        # - - -
        oh[ohWid[0], :] = timestamp, order_param, order_id, nPrice, nQty, nCommission
        ohWid[0] += 1
        if ohWid[0] >= oh.shape[0]:
            old_rows: int = oh.shape[0]
            self.orders_history = np.resize(
                oh, new_shape=((old_rows + self.oh_rows), self.oh_cols)
            )
            self.orders_history[old_rows:, :] = 0

    def update_position(
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

        if (_.longNqty == 0) and (_.shortNqty == 0):
            if _.lockedNbalance > 0:
                _.lockedNbalance = -(_.lockedNbalance)

    def final_action(self) -> None:
        if self.con.cfgAC.save_orders_history:
            np.save(c.ORDERS_HISTORY_DUMP_PATH, self.orders_history[: self.ohWid[0], :])
