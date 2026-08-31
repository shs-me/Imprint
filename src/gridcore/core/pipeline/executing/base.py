import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol, final

from ...exchange.account import Account, AccountConverter
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler


class ExecutionProtocol(Protocol):
    def action_for_getted_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None: ...

    def action_for_getted_executed_order(
        self,
        timestamp: int,
        order_param: int,
        order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None: ...


class SendOrderMethodSignature(Protocol):
    def __call__(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None: ...


@dataclass(slots=True)
class Base[T: Account](ABC):
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
    trade_readed_time: memoryview = field(init=False)
    readed_timestamp: int = field(default=0, init=False)
    con: AccountConverter = field(init=False)
    account: T = field(init=False)

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
        self.trade_readed_time = cfgMetrics.trade_readed_time.view.cast("q")
        self.__engine_complete = cfgMetrics.engine_complete.view

        self.con = AccountConverter(
            cfgAccount=self.manager.cfgAccount,
            cfgStrategy=self.manager.cfgRiskManagment,
            price_prec=self.manager.cfgCoin.price_prec,
            qty_prec=self.manager.cfgCoin.qty_prec,
        )

    @final
    @error_handler(set_status_code=True)
    def run(self) -> None:
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(scs.EXIT, wait_main_task=False)

                if task & scs.COMPLETE:
                    if self.__complete():
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
            (self.__engine_complete[0] == 1) and signals_readed and user_stream_readed
        )

    @final
    def __final_actions(self) -> None:
        self.post_final_action()

    @abstractmethod
    def post_final_action(self) -> None: ...

    @abstractmethod
    def alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None: ...

    @final
    def __check_signal_buf(
        self,
    ) -> None:
        nPrice, timestamp, order_param = self.__get_signal_data()
        self._check_user_data_buf()
        self.pre_execute_signal_action(timestamp)
        self._check_user_data_buf()
        if self.con.lossNbalanceSafeLimit:
            if self.con.lockedNbalanceSafeLimit:
                if (nominalNqty := self.con.nominalEntryNqtyWithLeverage) is not None:
                    if (timestamp + self.con.timer) <= self.readed_timestamp:
                        return

                    nQty: int = self.con.entryNqtyWithLeverage(nPrice, nominalNqty)
                    self.executor.action_for_getted_signal(
                        timestamp, order_param, nPrice, nQty
                    )
                else:
                    self.manager.set_proc_sc(
                        code=scs.QTY_LESS_LIMIT, wait_main_task=True
                    )
            else:
                pass
        else:
            self.post_final_action()
            self.manager.set_proc_sc(code=scs.LOSS_MORE_LIMIT, wait_main_task=True)

    @final
    def __get_signal_data(self) -> tuple[int, int, int]:
        cell: int = self.__sn_rid[0]
        start: int = cell * self.__sn_data_size
        get_data: memoryview = self.__sn_data[start : start + self.__sn_data_size]
        # signal_id = get_data[0]
        nPrice, timestamp, order_param = get_data[1], get_data[2], get_data[3]
        new_cell: int = cell + 1
        self.__sn_rid[0] = new_cell if (new_cell < self.__sn_cell_amount) else 0
        return nPrice, timestamp, order_param

    @abstractmethod
    def pre_execute_signal_action(self, time_get_signal: int) -> None: ...

    @final
    def _check_user_data_buf(self) -> None:
        while self.__gus_wid[0] != self.__gus_rid[0]:
            raw_buf = self.__get_user_data()
            self.preppare_user_data(raw_buf)

    @final
    def __get_user_data(self) -> memoryview:
        cell: int = self.__gus_rid[0]
        start: int = cell * self.__gus_data_size
        len_raw_data: int = self.__gus_data_header[cell]
        raw_data: memoryview = self.__gus_data[start : start + len_raw_data]
        new_cell: int = cell + 1
        self.__gus_rid[0] = new_cell if (new_cell < self.__gus_cell_amount) else 0
        return raw_data

    @abstractmethod
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None: ...

    @final
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
        self.account.update_local_lockedNbalance(nPrice, nQty, order_param)

    @final
    def __set_user_data(self, raw_data: bytes) -> None:
        cell: int = self.__sus_wid[0]
        start: int = cell * self.__sus_data_size
        self.__sus_data_header[cell] = len(raw_data)
        self.__sus_data[start : start + len(raw_data)] = raw_data
        new_cell: int = cell + 1
        self.__sus_wid[0] = new_cell if (new_cell < self.__sus_cell_amount) else 0
