import time
from dataclasses import dataclass
from typing import override

from imprint.api import constant as c
from imprint.api.base import BaseExecution


@dataclass
class HedgeExecution(BaseExecution):
    @override
    def action_for_getted_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        if self.con.is_averaging(order_param):
            return

        self.send_order(
            timestamp=time_get_signal + self.con.latency,
            order_param=order_param,
            client_order_id=self.con.newClientOrderId,
            nPrice=nPrice,
            nQty=nQty,
        )
        self.con.have_pending_orders = True
        self.count_open_positions[0] += 1

    @override
    def action_for_getted_executed_order(
        self,
        timestamp: int,
        order_param: int,
        order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        is_long, is_buy = (
            bool(order_param & c.OF_LONG),
            bool(order_param & c.OF_BUY),
        )
        if bool(order_param & c.OF_FILLED):
            is_open = (is_long and is_buy) or (not is_long and not is_buy)
            if is_open:
                self.con.have_pending_orders = False
                if self.is_backtesting:
                    tp_sl_timestamp = timestamp + self.con.latency
                else:
                    tp_sl_timestamp = round(time.time() * 1000)

                tp_nPrice, tp_order_param = self.con.tp_sl_param(
                    nPrice, is_long, True
                )
                self.send_order(
                    tp_sl_timestamp, tp_order_param, order_id, tp_nPrice, nQty
                )

                sl_nPrice, sl_order_param = self.con.tp_sl_param(
                    nPrice, is_long, False
                )
                self.send_order(
                    tp_sl_timestamp, sl_order_param, order_id, sl_nPrice, nQty
                )

        elif bool(order_param & c.OF_CANCELED):
            pass
