from abc import ABC, abstractmethod

from ...footprint.engine import FootprintEngine
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler


class Base(ABC):
    def __init__(self, manager: NodeManager, engine: FootprintEngine) -> None:
        self.manager: NodeManager = manager
        self.engine: FootprintEngine = engine

        cfgDS = self.manager.cfgDataStream
        self.ds_cell_amount: int = cfgDS.cell_amount
        self.ds_data_size: int = cfgDS.data_size
        self.ds_data: memoryview = cfgDS.data.view
        self.ds_data_header: memoryview = cfgDS.data_header.view
        self.ds_wid: memoryview = cfgDS.writer_id.view.cast("q")
        self.ds_rid: memoryview = cfgDS.reader_id.view.cast("q")

        cfgMetrics = self.manager.cfgMetrics
        self.engine_complete: memoryview = cfgMetrics.engine_complete.view

        self.nPrice: memoryview = memoryview(bytearray(8)).cast("q")
        self.nQty: memoryview = memoryview(bytearray(8)).cast("q")
        self.timestamp: memoryview = memoryview(bytearray(8)).cast("q")
        self.is_sell: memoryview = memoryview(bytearray(8)).cast("q")

    @error_handler(set_status_code=True)
    def run_engine(self) -> None:
        while True:
            while True:
                if self.manager.have_status():
                    task: int = self.manager.check_base_task()
                    if task & scs.EXIT:
                        return self.manager.set_proc_sc(scs.EXIT, wait_main_task=False)

                    if task & scs.COMPLETE:
                        if self.complete():
                            self.final_actions()
                            return self.manager.set_proc_sc(
                                scs.COMPLETE, wait_main_task=False
                            )

                if self.ds_wid[0] == self.ds_rid[0]:
                    self.alarm_clock()

                if self.ds_wid[0] != self.ds_rid[0]:
                    if self.get_trade_data():
                        self.engine._update_footprint(
                            self.nPrice[0],
                            self.nQty[0],
                            self.timestamp[0],
                            self.is_sell[0],
                        )

                        if self.ds_wid[0] != self.ds_rid[0]:
                            if not self.engine._tick_by_tick_analyze:
                                if not self.engine._re_init_session:
                                    continue

                        self.engine._analyze_footprint()

                        if self.engine._re_init_session:
                            self.engine._update_footprint(
                                self.nPrice[0],
                                self.nQty[0],
                                self.timestamp[0],
                                self.is_sell[0],
                            )

                        self.post_update()

    def complete(self) -> bool:
        return self.ds_wid[0] == self.ds_rid[0]

    def final_actions(self) -> None:
        self.engine_complete[0] = 1
        self.post_final_action()
        self.manager.set_text(
            (
                f"Count Prepped Ticks: {self.engine._counter_ticks} "
                f"Count Signals: {self.engine._sync._count_send_signal}"
            )
        )

    @abstractmethod
    def post_final_action(self) -> None:
        pass

    @abstractmethod
    def alarm_clock(self) -> None:
        pass

    def get_trade_data(self) -> bool:
        cell: int = self.ds_rid[0]
        lrd: int = self.ds_data_header[cell]
        start: int = cell * self.ds_data_size
        new_cell: int = cell + 1
        self.set_trade_data(self.ds_data[start : start + lrd])
        self.ds_rid[0] = new_cell if new_cell < self.ds_cell_amount else 0

        if (self.nPrice[0] > 0) and (self.nQty[0] > 0) and (self.timestamp[0] > 0):
            return True

        self.manager.set_proc_sc(code=scs.UNVALID_DATA, wait_main_task=True)

        return False

    @abstractmethod
    def set_trade_data(self, raw_data: memoryview) -> None:
        pass

    @abstractmethod
    def post_update(self) -> None:
        pass
