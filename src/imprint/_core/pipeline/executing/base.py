from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final

from imprint._core import constant as c
from imprint._core.account import Account
from imprint._core.ipc import NodeManager, node_handler
from imprint._core.settings import PositionFSM
from imprint._core.settings import StatusCodes as scs
from imprint._core.types import ExecutionProtocol


@dataclass(slots=True)
class Base(ABC):
    """Executes pipeline steps, managing node signals, user data buffers, and order flows.

    Parameters
    ----------
    manager : NodeManager
        Manager coordinating process states, tasks, and communication streams.
    engine : ExecutionProtocol
        Protocol implementation handling orders, signals, and execution callbacks.

    Attributes
    ----------
    manager : NodeManager
        Manager coordinating process states, tasks, and communication streams.
    executor : ExecutionProtocol
        Protocol implementation handling orders, signals, and execution callbacks.
    count_open_positions : memoryview
        Memory-mapped 64-bit signed integer tracking the count of currently open positions.
    trade_read_time : memoryview
        Memory view pointing to trade read time metrics.
    readed_timestamp : int
        Timestamp of the last read operation, defaulting to 0.
    account : Account
        Account state and balance risk management handler.
    """

    manager: NodeManager
    strategy: ExecutionProtocol

    trade_read_time: memoryview = field(init=False)
    __engine_complete: memoryview = field(init=False)
    account: Account = field(init=False)

    readed_timestamp: int = field(default=0, init=False)
    count_open_positions: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    def __post_init__(self) -> None:
        """Initialize pipeline streams, metrics views, and account instance."""
        cfgMetrics = self.manager.cfgMetrics
        self.trade_read_time = cfgMetrics.trade_read_time.view.cast("q")
        self.__engine_complete = cfgMetrics.engine_complete.view

        self.account = Account(self.manager)

    @final
    @node_handler()
    def run(self) -> None:
        """Execute the main processing loop handling tasks, signals, and user data."""
        u = self.manager.cfgUserDataStream.ring_buf
        s = self.manager.cfgSignalStream.ring_buf
        # - - -
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(
                        scs.EXIT, wait_main_task=False
                    )

                if task & scs.COMPLETE and self.__complete():
                    self.__final_actions()
                    return self.manager.set_proc_sc(
                        scs.COMPLETE, wait_main_task=False
                    )

            if self.__engine_complete[0] == 0:
                self.alarm_clock(s.wid_buf, s.rid_buf, u.wid_buf, u.rid_buf)

            if s.wid_buf[0] != s.rid_buf[0]:
                self.__check_signal_buf()
            elif u.wid_buf[0] != u.rid_buf[0]:
                self._check_user_data_buf()

    def reset(self) -> None:
        self.readed_timestamp, self.count_open_positions[0] = 0, 0
        self.account.reset()

    @final
    def __complete(self) -> bool:
        """Check whether execution engine is complete and ring buffers are fully drained.

        Returns
        -------
        bool
            True if engine completion flag is set and both signal and user data
            write/read pointers are aligned.
        """
        u = self.manager.cfgUserDataStream.ring_buf
        s = self.manager.cfgSignalStream.ring_buf
        # - - -
        return (
            (self.__engine_complete[0] == 1)
            and (s.wid_buf[0] == s.rid_buf[0])
            and (u.wid_buf[0] == u.rid_buf[0])
        )

    @final
    def __final_actions(self) -> None:
        """Execute final cleanup actions upon completion."""
        self.post_final_action()

    @abstractmethod
    def post_final_action(self) -> None:
        """Execute subclass-specific actions upon pipeline completion."""

    @abstractmethod
    def alarm_clock(
        self,
        WB_1: memoryview,
        RB_1: memoryview,
        WB_2: memoryview,
        RB_2: memoryview,
    ) -> None:
        """Handle timeout or periodic alarm events using ring buffer pointers.

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

    @final
    def __check_signal_buf(
        self,
    ) -> None:
        """Read and process incoming trading signals from the signal ring buffer."""
        signal_id, nPrice, timestamp, order_param, tp_dev, sl_dev = (
            self.manager.cfgSignalStream.ring_buf.get_data()
        )
        self._check_user_data_buf()
        self.pre_execute_signal_action(timestamp)
        self._check_user_data_buf()
        if self.account.lossNbalanceSafeLimit:
            if self.account.lockedNbalanceSafeLimit:
                if (
                    nominalNqty := self.account.nominalEntryNqtyWithLeverage
                ) is not None:
                    if (
                        (timestamp + self.account.time_for_expired_signal)
                        <= self.readed_timestamp
                    ) or self.account.is_averaging(order_param):
                        return

                    nQty: int = self.account.entryNqtyWithLeverage(
                        nPrice, nominalNqty
                    )
                    self.strategy.on_signal(
                        signal_id=signal_id,
                        time_get_signal=timestamp,
                        order_param=order_param,
                        nPrice=nPrice,
                        nQty=nQty,
                        tp_dev=tp_dev,
                        sl_dev=sl_dev,
                    )

                else:
                    self.manager.set_proc_sc(
                        code=scs.QTY_LESS_LIMIT, wait_main_task=True
                    )
            else:
                pass
        else:
            self.post_final_action()
            self.manager.set_proc_sc(
                code=scs.LOSS_MORE_LIMIT, wait_main_task=True
            )

    @abstractmethod
    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        """Execute subclass-specific logic prior to signal processing.

        Parameters
        ----------
        time_get_signal : int
            Timestamp when the signal was received, in microseconds or milliseconds.
        """

    @final
    def _check_user_data_buf(self) -> None:
        """Drain and process all available items in the user data ring buffer."""
        _ = self.manager.cfgUserDataStream.ring_buf
        # - - -
        while _.wid_buf[0] != _.rid_buf[0]:
            self.preppare_user_data(_.get_data())

    @abstractmethod
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        """Process a raw user data buffer retrieved from the ring buffer.

        Parameters
        ----------
        user_data_raw_buf : memoryview
            Raw byte memory view containing user data payload.
        """

    @final
    def on_order_update(
        self,
        timestamp: int,
        order_param: int,
        order_id: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        """Handle incoming order update events and update position FSM states.

        Parameters
        ----------
        timestamp : int
            Timestamp of the order update event.
        order_param : int
            Bitfield flags containing order parameters and status flags.
        order_id : int
            Unique exchange-assigned order identifier.
        client_order_id : int
            Unique client-assigned order identifier.
        nPrice : int
            Normalized order price.
        nQty : int
            Normalized order quantity.
        nCommission : int
            Normalized commission fee associated with the order.
        """
        is_long: bool = bool(order_param & c.OF_LONG)
        is_buy: bool = bool(order_param & c.OF_BUY)
        is_open: bool = (is_long and is_buy) or (not is_long and not is_buy)
        if bool(order_param & c.OF_FILLED):
            if is_open:
                if is_long:
                    self.account.long = PositionFSM.OPEN
                else:
                    self.account.short = PositionFSM.OPEN

                self.count_open_positions[0] += 1
            else:
                if is_long:
                    self.account.long = PositionFSM.CLOSE
                else:
                    self.account.short = PositionFSM.CLOSE

            self.strategy.on_filled_order(
                timestamp=timestamp,
                is_long=is_long,
                is_buy=is_buy,
                order_id=order_id,
                client_order_id=client_order_id,
                nPrice=nPrice,
                nQty=nQty,
                nCommission=nCommission,
            )

        elif bool(order_param & c.OF_CANCELED):
            if is_open:
                if is_long:
                    self.account.long = PositionFSM.EMPTY
                else:
                    self.account.short = PositionFSM.EMPTY

            self.strategy.on_canceled_order(
                timestamp=timestamp,
                is_long=is_long,
                is_buy=is_buy,
                order_id=order_id,
                client_order_id=client_order_id,
                nPrice=nPrice,
                nQty=nQty,
                nCommission=nCommission,
            )

    @final
    def on_balance_update(
        self, nBalance: int, lockedNbalance: int, availableNbalance: int
    ) -> None:
        """Update account balance and locked/available balance metrics.

        Parameters
        ----------
        nBalance : int
            Normalized total account balance.
        lockedNbalance : int
            Normalized locked balance in open orders or positions.
        availableNbalance : int
            Normalized available balance for new trades.
        """
        self.account.nBalance[0] = nBalance
        self.account.lockedNbalance[0] = lockedNbalance
        self.account.availableNbalance[0] = availableNbalance

    def send_order(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        """Publish a new order instruction to the order stream.

        Parameters
        ----------
        timestamp : int
            Timestamp when the order request was generated.
        order_param : int
            Bitfield flags specifying order type, side, and characteristics.
        client_order_id : int
            Unique client-assigned order identifier.
        nPrice : int
            Normalized limit or stop price.
        nQty : int
            Normalized order quantity.
        """
        self.manager.cfgOrderStream.set_data(
            timestamp=timestamp,
            order_param=order_param,
            client_order_id=client_order_id,
            nPrice=nPrice,
            nQty=nQty,
        )

        if order_param & c.OF_NEW:
            is_long: int = order_param & c.OF_LONG
            is_buy: int = order_param & c.OF_BUY
            if (is_long and is_buy) or (not is_long and not is_buy):
                if is_long:
                    self.account.long = PositionFSM.PENDING
                else:
                    self.account.short = PositionFSM.PENDING
