import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final

from imprint.core import constant as c
from imprint.core.account import Account
from imprint.core.ipc import NodeManager, node_handler
from imprint.core.settings import ExecutionProtocol, PositionFSM
from imprint.core.settings import StatusCodes as scs


@dataclass(slots=True)
class Base(ABC):
    manager: NodeManager
    executor: ExecutionProtocol

    __sn_cell_amount: int = field(init=False)
    __sn_data_size: int = field(init=False)
    __sn_data: memoryview = field(init=False)
    __sn_wid: memoryview = field(init=False)
    __sn_rid: memoryview = field(init=False)

    __gus_cell_amount: int = field(init=False)
    __gus_data: memoryview = field(init=False)
    __gus_data_size: int = field(init=False)
    __gus_data_header: memoryview = field(init=False)
    __gus_wid: memoryview = field(init=False)
    __gus_rid: memoryview = field(init=False)

    __sus_cell_amount: int = field(init=False)
    __sus_data: memoryview = field(init=False)
    __sus_data_size: int = field(init=False)
    __sus_data_header: memoryview = field(init=False)
    __sus_wid: memoryview = field(init=False)
    __sus_rid: memoryview = field(init=False)

    __engine_complete: memoryview = field(init=False)

    count_open_positions: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    trade_read_time: memoryview = field(init=False)
    readed_timestamp: int = field(default=0, init=False)
    account: Account = field(init=False)

    @final
    def __post_init__(self) -> None:
        cfgSN = self.manager.cfgSignal
        self.__sn_cell_amount = cfgSN.cell_amount
        self.__sn_data_size = cfgSN.data_size // 8
        self.__sn_data = cfgSN.data.view.cast("q")
        self.__sn_wid = cfgSN.writer_id.view.cast("q")
        self.__sn_rid = cfgSN.reader_id.view.cast("q")

        cfgGUS = self.manager.cfgGetUserStream
        self.__gus_cell_amount = cfgGUS.cell_amount
        self.__gus_data = cfgGUS.data.view
        self.__gus_data_size = cfgGUS.data_size
        self.__gus_data_header = cfgGUS.data_header.view
        self.__gus_wid = cfgGUS.writer_id.view.cast("q")
        self.__gus_rid = cfgGUS.reader_id.view.cast("q")

        cfgSUS = self.manager.cfgSetUserStream
        self.__sus_cell_amount = cfgSUS.cell_amount
        self.__sus_data = cfgSUS.data.view
        self.__sus_data_size = cfgSUS.data_size
        self.__sus_data_header = cfgSUS.data_header.view
        self.__sus_wid = cfgSUS.writer_id.view.cast("q")
        self.__sus_rid = cfgSUS.reader_id.view.cast("q")

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
                self.alarm_clock(
                    self.__sn_wid, self.__sn_rid, self.__gus_wid, self.__gus_rid
                )

            if self.__sn_wid[0] != self.__sn_rid[0]:
                self.__check_signal_buf()
            elif self.__gus_wid[0] != self.__gus_rid[0]:
                self._check_user_data_buf()

    @final
    def __complete(self) -> bool:
        signals_readed: bool = self.__sn_wid[0] == self.__sn_rid[0]
        user_stream_readed: bool = self.__gus_wid[0] == self.__gus_rid[0]
        return (
            (self.__engine_complete[0] == 1)
            and signals_readed
            and user_stream_readed
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
        signal_id, nPrice, timestamp, order_param = self.__get_signal_data()
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

    @final
    def __get_signal_data(self) -> tuple[int, int, int, int]:
        cell: int = self.__sn_rid[0]
        start: int = cell * self.__sn_data_size
        get_data: memoryview = self.__sn_data[
            start : start + self.__sn_data_size
        ]
        signal_id = get_data[0]
        nPrice, timestamp, order_param = get_data[1], get_data[2], get_data[3]
        new_cell: int = cell + 1
        self.__sn_rid[0] = new_cell if (new_cell < self.__sn_cell_amount) else 0
        return signal_id, nPrice, timestamp, order_param

    @abstractmethod
    def pre_execute_signal_action(self, time_get_signal: int) -> None: ...

    @final
    def _check_user_data_buf(self) -> None:
        while self.__gus_wid[0] != self.__gus_rid[0]:
            self.__get_user_data()

    @final
    def __get_user_data(self) -> None:
        cell: int = self.__gus_rid[0]
        start: int = cell * self.__gus_data_size
        len_raw_data: int = self.__gus_data_header[cell]

        raw_data: memoryview = self.__gus_data[start : start + len_raw_data]
        self.preppare_user_data(raw_data)

        new_cell: int = cell + 1
        self.__gus_rid[0] = (
            new_cell if (new_cell < self.__gus_cell_amount) else 0
        )

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

    def send_order(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        raw_data: bytes = struct.pack(
            "@qqqqq", timestamp, order_param, client_order_id, nPrice, nQty
        )
        self.__set_user_data(raw_data)

        if order_param & c.OF_NEW:
            is_long: int = order_param & c.OF_LONG
            is_buy: int = order_param & c.OF_BUY
            if (is_long and is_buy) or (not is_long and not is_buy):
                if is_long:
                    self.account.long = PositionFSM.PENDING
                else:
                    self.account.short = PositionFSM.PENDING

    @final
    def __set_user_data(self, raw_data: bytes) -> None:
        cell: int = self.__sus_wid[0]
        start: int = cell * self.__sus_data_size
        self.__sus_data_header[cell] = len(raw_data)
        self.__sus_data[start : start + len(raw_data)] = raw_data
        new_cell: int = cell + 1
        self.__sus_wid[0] = (
            new_cell if (new_cell < self.__sus_cell_amount) else 0
        )
