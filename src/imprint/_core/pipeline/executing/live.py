import time
from dataclasses import dataclass
from multiprocessing.synchronize import Event, Semaphore
from typing import override

from imprint._core import constant as c
from imprint._core.pipeline.executing.base import Base


@dataclass(slots=True)
class Live(Base):
    execution_event: Event
    wss_sem: Semaphore

    @override
    def child_post_init(self) -> None: ...

    @override
    def alarm_clock(
        self,
        WB_1: memoryview,
        RB_1: memoryview,
        WB_2: memoryview,
        RB_2: memoryview,
    ) -> None:
        """Blocks process on execution_event when ring buffers are drained."""

        if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
            self.execution_event.clear()
            if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
                self.execution_event.wait(timeout=0.1)

    @override
    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        self.readed_timestamp: int = round(time.time() * 1000)

    @override
    def send_order(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        Base.send_order(
            self, timestamp, order_param, client_order_id, nPrice, nQty
        )
        self.wss_sem.release()

    @override
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        if len(user_data_raw_buf) > 2:
            timestamp: int = user_data_raw_buf[c.TP_timestamp]
            order_param: int = user_data_raw_buf[c.TP_order_param]
            order_id: int = user_data_raw_buf[c.TP_order_id]
            client_order_id: int = user_data_raw_buf[c.TP_client_order_id]
            nPrice: int = user_data_raw_buf[c.TP_nPrice]
            nQty: int = user_data_raw_buf[c.TP_nQty]
            nCommission: int = user_data_raw_buf[c.TP_nCommission]

            self.on_order_update(
                timestamp=timestamp,
                order_param=order_param,
                order_id=order_id,
                client_order_id=client_order_id,
                nPrice=nPrice,
                nQty=nQty,
                nCommission=nCommission,
            )
        else:
            nBalance: int = user_data_raw_buf[0]
            lockedNbalance: int = user_data_raw_buf[1]
            availableNbalance: int = user_data_raw_buf[1]

            self.on_balance_update(nBalance, lockedNbalance, availableNbalance)

    @override
    def post_final_action(self) -> None: ...
