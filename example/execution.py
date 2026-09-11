import time
from dataclasses import dataclass
from typing import override

from imprint import constant as c
from imprint.configs import BaseExecution


@dataclass(slots=True)
class HedgeExecution(BaseExecution):
    @override
    def on_signal(
        self,
        signal_id: int,
        time_get_signal: int,
        order_param: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        self.send_order(
            timestamp=time_get_signal,
            order_param=order_param,
            client_order_id=signal_id,
            nPrice=nPrice,
            nQty=nQty,
        )

    @override
    def on_filled_order(
        self,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        order_id: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        new_order_timestamp: int = (
            timestamp if self.is_backtesting else round(time.time() * 1000)
        )
        is_open: bool = (is_long and is_buy) or (not is_long and not is_buy)
        if is_open:
            tp_nPrice, tp_order_param, tp_client_order_id = (
                self.account.tp_sl_param(
                    nPrice, client_order_id, is_long, is_tp=True
                )
            )
            self.send_order(
                timestamp=new_order_timestamp,
                order_param=tp_order_param,
                client_order_id=tp_client_order_id,
                nPrice=tp_nPrice,
                nQty=nQty,
            )

            sl_nPrice, sl_order_param, sl_client_order_id = (
                self.account.tp_sl_param(
                    nPrice, client_order_id, is_long, is_tp=False
                )
            )
            self.send_order(
                timestamp=new_order_timestamp,
                order_param=sl_order_param,
                client_order_id=sl_client_order_id,
                nPrice=sl_nPrice,
                nQty=nQty,
            )
        else:
            if self.account.is_tp_client_order_id(client_order_id):
                client_order_id = self.account.to_sl_client_order_id(
                    client_order_id
                )
            else:
                client_order_id = self.account.to_tp_client_order_id(
                    client_order_id
                )

            order_param: int = c.OF_CANCEL
            self.send_order(
                timestamp=new_order_timestamp,
                order_param=order_param,
                client_order_id=client_order_id,
                nPrice=0,
                nQty=0,
            )

    @override
    def on_canceled_order(
        self,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        order_id: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None: ...
