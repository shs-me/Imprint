from dataclasses import dataclass
from multiprocessing.synchronize import Event
from typing import override

from imprint.core.exchange.account import Account
from imprint.core.pipeline.executing.base import Base


@dataclass(slots=True)
class Live(Base[Account]):
    execution_event: Event

    @override
    def init_session(self) -> None: ...

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
        pass

    @override
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:

        data = user_data_raw_buf.cast("q")
        event_type = data[1]

        if event_type == 1:
            timestamp: int = data[0]
            order_param: int = data[2]
            order_id: int = data[3]
            nPrice: int = data[4]
            nQty: int = data[5]
            nCommission: int = data[6]

            self.executor.on_order_update(
                timestamp, order_param, order_id, nPrice, nQty, nCommission
            )
            self.con.update_orders_history(
                timestamp,
                order_param,
                order_id,
                nPrice,
                nQty,
                nCommission,
                0,
                0,
            )

        elif event_type == 2:
            pass

    @override
    def post_final_action(self) -> None:
        pass
