import time
from dataclasses import dataclass
from multiprocessing.synchronize import Event, Semaphore
from typing import override

from imprint._core import constant as c
from imprint._core.pipeline.executing.base import Base


@dataclass(slots=True)
class Live(Base):
    """Executes live trading pipeline steps with multiprocessing synchronization.

    Parameters
    ----------
    execution_event : Event
        Multiprocessing event used to block execution when ring buffers are drained.
    wss_sem : Semaphore
        Multiprocessing semaphore released upon sending orders.

    Attributes
    ----------
    execution_event : Event
        Multiprocessing event used to block execution when ring buffers are drained.
    wss_sem : Semaphore
        Multiprocessing semaphore released upon sending orders.
    """

    execution_event: Event
    wss_sem: Semaphore

    @override
    def alarm_clock(
        self,
        WB_1: memoryview,
        RB_1: memoryview,
        WB_2: memoryview,
        RB_2: memoryview,
    ) -> None:
        """Block process on execution_event when ring buffers are drained.

        Parameters
        ----------
        WB_1 : memoryview
            Write pointer buffer for the signal stream ring buffer.
        RB_1 : memoryview
            Read pointer buffer for the signal stream ring buffer.
        WB_2 : memoryview
            Write pointer buffer for the user data stream ring buffer.
        RB_2 : memoryview
            Read pointer buffer for the user data stream ring buffer.
        """

        if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
            self.execution_event.clear()
            if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
                self.execution_event.wait(timeout=0.1)

    @override
    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        """Update read timestamp with current system epoch time in milliseconds.

        Parameters
        ----------
        time_get_signal : int
            Timestamp when the signal was received, in milliseconds.
        """
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
        """Publish order to stream and release WebSocket semaphore.

        Parameters
        ----------
        timestamp : int
            Timestamp when the order request was generated.
        order_param : int
            Bitfield flags specifying order type, side, and characteristics.
        client_order_id : int
            Unique client-assigned order identifier.
        nPrice : int
            Normalized order price.
        nQty : int
            Normalized order quantity.
        """
        Base.send_order(
            self, timestamp, order_param, client_order_id, nPrice, nQty
        )
        self.wss_sem.release()

    @override
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        """Process raw user data buffer into order or balance updates.

        Parameters
        ----------
        user_data_raw_buf : memoryview
            Raw byte memory view containing user data payload.
        """
        if len(user_data_raw_buf) > 3:
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
            availableNbalance: int = user_data_raw_buf[2]

            self.on_balance_update(nBalance, lockedNbalance, availableNbalance)

    @override
    def post_final_action(self) -> None:
        """Execute final cleanup actions upon completion."""
