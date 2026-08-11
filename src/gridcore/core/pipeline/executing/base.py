import struct
from abc import ABC, abstractmethod

from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler
from .account import AccountConverter, AccountManager


class Base(ABC):
    def __init__(self, manager: NodeManager) -> None:
        self.manager: NodeManager = manager

        self.set_proc_sc = manager.set_proc_sc
        self.have_status = manager.have_status
        self.task_status = manager.task_status
        self.check_base_task = manager.check_base_task

        cfgSN = manager.cfgSignal
        self.sn_cell_amount: int = cfgSN.cell_amount
        self.sn_data_size: int = cfgSN.data_size // 8
        self.sn_data: memoryview = cfgSN.data.cast("q")
        self.sn_wid: memoryview = cfgSN.writer_id.cast("q")
        self.sn_rid: memoryview = cfgSN.reader_id.cast("q")

        cfgGUS = manager.cfgGetUserStream
        self.gus_cell_amount: int = cfgGUS.cell_amount
        self.gus_data: memoryview = cfgGUS.data
        self.gus_data_size: int = cfgGUS.data_size
        self.gus_data_header: memoryview = cfgGUS.data_header
        self.gus_wid: memoryview = cfgGUS.writer_id.cast("q")
        self.gus_rid: memoryview = cfgGUS.reader_id.cast("q")

        cfgSUS = manager.cfgSetUserStream
        self.sus_cell_amount: int = cfgSUS.cell_amount
        self.sus_data: memoryview = cfgSUS.data
        self.sus_data_size: int = cfgSUS.data_size
        self.sus_data_header: memoryview = cfgSUS.data_header
        self.sus_wid: memoryview = cfgSUS.writer_id.cast("q")
        self.sus_rid: memoryview = cfgSUS.reader_id.cast("q")

        cfgMetrics = manager.cfgMetrics
        self.trade_readed_time: memoryview = cfgMetrics.trade_readed_time.cast("q")
        self.logic_complete: memoryview = cfgMetrics.logic_complete

        self.symbol: str = manager.cfgCoin.symbol
        self.con: AccountConverter = AccountConverter(
            cfgAccount=manager.cfgAccount,
            cfgStrategy=manager.cfgRiskManagment,
            price_prec=manager.cfgCoin.price_prec,
            qty_prec=manager.cfgCoin.qty_prec,
        )
        self.acm = AccountManager(manager)
        self.readed_timestamp: int = 0

    @error_handler(set_status_code=True)
    def _run_execution_engine(self) -> None:
        # LocalLinks
        WB_1, RB_1, WB_2, RB_2 = self.sn_wid, self.sn_rid, self.gus_wid, self.gus_rid
        # - - -
        while True:
            # - - -
            while True:
                if self.have_status():
                    task: bool | int = self.check_base_task(complete=self._complete())
                    if isinstance(task, bool):
                        if task:
                            if self.task_status[0] & scs.COMPLETE:
                                self._final_actions()
                                self.set_proc_sc(scs.COMPLETE, wait_main_task=False)
                            return

                if self.logic_complete[0] == 0:
                    self._alarm_clock(WB_1, RB_1, WB_2, RB_2)

                if WB_1[0] != RB_1[0]:
                    self._check_signal_buf()
                elif WB_2[0] != RB_2[0]:
                    self._check_user_data_buf()

    def _complete(self) -> bool:
        return (self.logic_complete[0] == 1) and (
            (self.sn_wid[0] == self.sn_rid[0]) and (self.gus_wid[0] == self.gus_rid[0])
        )

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
                    if (timestamp + self.con.timer) <= self.readed_timestamp:
                        return

                    nQty: int = self.con.entryNqtyWithLeverage(nPrice, nominalNqty)
                    self.action_for_getted_signal(timestamp, order_param, nPrice, nQty)
                else:
                    self.set_proc_sc(code=scs.QTY_LESS_LIMIT, wait_main_task=True)
            else:
                pass
        else:
            self.set_proc_sc(code=scs.LOSS_MORE_LIMIT, wait_main_task=True)
            self._post_final_action()

    def _get_signal_data(self) -> tuple[int, int, int]:
        cell: int = self.sn_rid[0]
        start: int = cell * self.sn_data_size
        get_data: memoryview = self.sn_data[start : start + self.sn_data_size]
        signal_id = get_data[0]
        nPrice, timestamp, order_param = get_data[1], get_data[2], get_data[3]
        new_cell: int = cell + 1
        self.sn_rid[0] = new_cell if (new_cell < self.sn_cell_amount) else 0
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
        while self.gus_wid[0] != self.gus_rid[0]:
            raw_buf = self._get_user_data()
            self._preppare_user_data(raw_buf)

    def _get_user_data(self) -> memoryview:
        cell: int = self.gus_rid[0]
        start: int = cell * self.gus_data_size
        len_raw_data: int = self.gus_data_header[cell]
        raw_data: memoryview = self.gus_data[start : start + len_raw_data]
        new_cell: int = cell + 1
        self.gus_rid[0] = new_cell if (new_cell < self.gus_cell_amount) else 0
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
        cell: int = self.sus_wid[0]
        start: int = cell * self.sus_data_size
        self.sus_data_header[cell] = len(raw_data)
        self.sus_data[start : start + len(raw_data)] = raw_data
        new_cell: int = cell + 1
        self.sus_wid[0] = new_cell if (new_cell < self.sus_cell_amount) else 0

    def _final_actions(self) -> None:
        self._post_final_action()

    @abstractmethod
    def _post_final_action(self) -> None:
        pass
