from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final

from imprint._core import constant as c
from imprint._core.account import Account
from imprint._core.configs import OrderStream, SignalStream, UserDataStream
from imprint._core.ipc import NodeManager, node_handler
from imprint._core.settings import PositionFSM
from imprint._core.settings import StatusCodes as scs
from imprint._core.types import ExecutionProtocol


@dataclass(slots=True)
class Base(ABC):
    manager: NodeManager
    executor: ExecutionProtocol

    __ss: SignalStream = field(init=False)
    __uds: UserDataStream = field(init=False)
    __os: OrderStream = field(init=False)

    __engine_complete: memoryview = field(init=False)

    count_open_positions: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    trade_read_time: memoryview = field(init=False)
    readed_timestamp: int = field(default=0, init=False)
    account: Account = field(init=False)

    @final
    def __post_init__(self) -> None:
        self.__ss = self.manager.cfgSignalStream
        self.__uds = self.manager.cfgUserDataStream
        self.__os = self.manager.cfgOrderStream

        cfgMetrics = self.manager.cfgMetrics
        self.trade_read_time = cfgMetrics.trade_read_time.view.cast("q")
        self.__engine_complete = cfgMetrics.engine_complete.view

        self.account = Account(self.manager)
        self.child_post_init()

    @abstractmethod
    def child_post_init(self) -> None: ...

    @final
    @node_handler()
    def run(self) -> None:
        u, s = self.__uds.ring_buf, self.__ss.ring_buf
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

    @final
    def __complete(self) -> bool:
        u, s = self.__uds.ring_buf, self.__ss.ring_buf
        return (
            (self.__engine_complete[0] == 1)
            and (s.wid_buf[0] == s.rid_buf[0])
            and (u.wid_buf[0] == u.rid_buf[0])
        )

    @final
    def __final_actions(self) -> None:
        self.post_final_action()

    @abstractmethod
    def post_final_action(self) -> None: ...

    @abstractmethod
    def alarm_clock(
        self,
        WB_1: memoryview,
        RB_1: memoryview,
        WB_2: memoryview,
        RB_2: memoryview,
    ) -> None: ...

    @final
    def __check_signal_buf(
        self,
    ) -> None:
        signal_id, nPrice, timestamp, order_param = (
            self.__ss.ring_buf.get_data()
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
                    self.executor.on_signal(
                        signal_id, timestamp, order_param, nPrice, nQty
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
    def pre_execute_signal_action(self, time_get_signal: int) -> None: ...

    @final
    def _check_user_data_buf(self) -> None:
        _ = self.__uds.ring_buf
        while _.wid_buf[0] != _.rid_buf[0]:
            self.preppare_user_data(_.get_data())

    @abstractmethod
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None: ...

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

            self.executor.on_filled_order(
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

            self.executor.on_canceled_order(
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
        self.__os.ring_buf.set_data(
            timestamp, order_param, client_order_id, nPrice, nQty
        )

        if order_param & c.OF_NEW:
            is_long: int = order_param & c.OF_LONG
            is_buy: int = order_param & c.OF_BUY
            if (is_long and is_buy) or (not is_long and not is_buy):
                if is_long:
                    self.account.long = PositionFSM.PENDING
                else:
                    self.account.short = PositionFSM.PENDING
