import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ...account import AccountConverter, AccountManager
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler


@dataclass
class Base(ABC):
    _manager: NodeManager

    _sn_cell_amount: int = field(init=False)
    _sn_data_size: int = field(init=False)
    _sn_data: memoryview = field(init=False)
    _sn_wid: memoryview = field(init=False)
    _sn_rid: memoryview = field(init=False)

    _gus_cell_amount: int = field(init=False)
    _gus_data: memoryview = field(init=False)
    _gus_data_size: int = field(init=False)
    _gus_data_header: memoryview = field(init=False)
    _gus_wid: memoryview = field(init=False)
    _gus_rid: memoryview = field(init=False)

    _sus_cell_amount: int = field(init=False)
    _sus_data: memoryview = field(init=False)
    _sus_data_size: int = field(init=False)
    _sus_data_header: memoryview = field(init=False)
    _sus_wid: memoryview = field(init=False)
    _sus_rid: memoryview = field(init=False)

    _trade_readed_time: memoryview = field(init=False)
    _engine_complete: memoryview = field(init=False)

    _readed_timestamp: int = field(default=0, init=False)

    count_open_positions: int = field(default=0, init=False)
    con: AccountConverter = field(init=False)
    acm: Any = field(init=False)

    def __post_init__(self) -> None:
        cfgSN = self._manager.cfgSignal
        self._sn_cell_amount = cfgSN.cell_amount
        self._sn_data_size = cfgSN.data_size // 8
        self._sn_data = cfgSN.data.view.cast("q")
        self._sn_wid = cfgSN.writer_id.view.cast("q")
        self._sn_rid = cfgSN.reader_id.view.cast("q")

        cfgGUS = self._manager.cfgGetUserStream
        self._gus_cell_amount = cfgGUS.cell_amount
        self._gus_data = cfgGUS.data.view
        self._gus_data_size = cfgGUS.data_size
        self._gus_data_header = cfgGUS.data_header.view
        self._gus_wid = cfgGUS.writer_id.view.cast("q")
        self._gus_rid = cfgGUS.reader_id.view.cast("q")

        cfgSUS = self._manager.cfgSetUserStream
        self._sus_cell_amount = cfgSUS.cell_amount
        self._sus_data = cfgSUS.data.view
        self._sus_data_size = cfgSUS.data_size
        self._sus_data_header = cfgSUS.data_header.view
        self._sus_wid = cfgSUS.writer_id.view.cast("q")
        self._sus_rid = cfgSUS.reader_id.view.cast("q")

        cfgMetrics = self._manager.cfgMetrics
        self._trade_readed_time = cfgMetrics.trade_readed_time.view.cast("q")
        self._engine_complete = cfgMetrics.engine_complete.view

        self.con = AccountConverter(
            cfgAccount=self._manager.cfgAccount,
            cfgStrategy=self._manager.cfgRiskManagment,
            price_prec=self._manager.cfgCoin.price_prec,
            qty_prec=self._manager.cfgCoin.qty_prec,
        )
        self.acm = AccountManager(self._manager)

    @error_handler(set_status_code=True)
    def _run_execution_engine(self) -> None:
        while True:
            if self._manager.have_status():
                task: int = self._manager.check_base_task()
                if task & scs.EXIT:
                    return self._manager.set_proc_sc(scs.EXIT, wait_main_task=False)

                if task & scs.COMPLETE:
                    if self._complete():
                        self._final_actions()
                        return self._manager.set_proc_sc(
                            scs.COMPLETE, wait_main_task=False
                        )

            if self._engine_complete[0] == 0:
                self._alarm_clock(
                    self._sn_wid, self._sn_rid, self._gus_wid, self._gus_rid
                )

            if self._sn_wid[0] != self._sn_rid[0]:
                self._check_signal_buf()
            elif self._gus_wid[0] != self._gus_rid[0]:
                self._check_user_data_buf()

    def _complete(self) -> bool:
        signals_readed: bool = self._sn_wid[0] == self._sn_rid[0]
        user_stream_readed: bool = self._gus_wid[0] == self._gus_rid[0]
        return (self._engine_complete[0] == 1) and signals_readed and user_stream_readed

    @abstractmethod
    def _alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        pass

    def _check_signal_buf(
        self,
    ) -> None:
        nPrice, timestamp, order_param = self._get_signal_data()
        self._check_user_data_buf()
        self._pre_execute_signal_action(timestamp)
        self._check_user_data_buf()
        if self.con.lossNbalanceSafeLimit:
            if self.con.lockedNbalanceSafeLimit:
                if (nominalNqty := self.con.nominalEntryNqtyWithLeverage) is not None:
                    if (timestamp + self.con.timer) <= self._readed_timestamp:
                        return

                    nQty: int = self.con.entryNqtyWithLeverage(nPrice, nominalNqty)
                    self.action_for_getted_signal(timestamp, order_param, nPrice, nQty)
                else:
                    self._manager.set_proc_sc(
                        code=scs.QTY_LESS_LIMIT, wait_main_task=True
                    )
            else:
                pass
        else:
            self._post_final_action()
            self._manager.set_proc_sc(code=scs.LOSS_MORE_LIMIT, wait_main_task=True)

    def _get_signal_data(self) -> tuple[int, int, int]:
        cell: int = self._sn_rid[0]
        start: int = cell * self._sn_data_size
        get_data: memoryview = self._sn_data[start : start + self._sn_data_size]
        # signal_id = get_data[0]
        nPrice, timestamp, order_param = get_data[1], get_data[2], get_data[3]
        new_cell: int = cell + 1
        self._sn_rid[0] = new_cell if (new_cell < self._sn_cell_amount) else 0
        return nPrice, timestamp, order_param

    @abstractmethod
    def _pre_execute_signal_action(self, time_get_signal: int) -> None:
        pass

    @abstractmethod
    def action_for_getted_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        pass

    def _check_user_data_buf(self) -> None:
        while self._gus_wid[0] != self._gus_rid[0]:
            raw_buf = self._get_user_data()
            self._preppare_user_data(raw_buf)

    def _get_user_data(self) -> memoryview:
        cell: int = self._gus_rid[0]
        start: int = cell * self._gus_data_size
        len_raw_data: int = self._gus_data_header[cell]
        raw_data: memoryview = self._gus_data[start : start + len_raw_data]
        new_cell: int = cell + 1
        self._gus_rid[0] = new_cell if (new_cell < self._gus_cell_amount) else 0
        return raw_data

    @abstractmethod
    def _preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        pass

    @abstractmethod
    def action_for_getted_executed_order(
        self,
        timestamp: int,
        order_param: int,
        order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        pass

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
        self._set_user_data(raw_data)
        self.acm.update_local_lockedNbalance(nPrice, nQty, order_param)

    def _set_user_data(self, raw_data: bytes) -> None:
        cell: int = self._sus_wid[0]
        start: int = cell * self._sus_data_size
        self._sus_data_header[cell] = len(raw_data)
        self._sus_data[start : start + len(raw_data)] = raw_data
        new_cell: int = cell + 1
        self._sus_wid[0] = new_cell if (new_cell < self._sus_cell_amount) else 0

    def _final_actions(self) -> None:
        self._post_final_action()

    @abstractmethod
    def _post_final_action(self) -> None:
        pass
