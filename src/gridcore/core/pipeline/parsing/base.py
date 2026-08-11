from abc import ABC, abstractmethod

from ...footprint import BaseFootprintWriter
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler


class Base(ABC):
    def __init__(self, manager: NodeManager, writer: BaseFootprintWriter) -> None:
        self.manager: NodeManager = manager
        self.writer: BaseFootprintWriter = writer

        self.set_proc_sc = manager.set_proc_sc
        self.have_status = manager.have_status
        self.task_status = manager.task_status
        self.check_base_task = manager.check_base_task

        cfgDS = self.manager.cfgDataStream
        self.ds_cell_amount: int = cfgDS.cell_amount
        self.ds_data_size: int = cfgDS.data_size
        self.ds_data: memoryview = cfgDS.data
        self.ds_data_header: memoryview = cfgDS.data_header
        self.ds_wid: memoryview = cfgDS.writer_id.cast("q")
        self.ds_rid: memoryview = cfgDS.reader_id.cast("q")

        cfgMetrics = self.manager.cfgMetrics
        self.parsing_complete: memoryview = cfgMetrics.parsing_complete

        self.price: memoryview[float] = memoryview(bytearray(8)).cast("d")
        self.qty: memoryview[float] = memoryview(bytearray(8)).cast("d")
        self.timestamp: memoryview = memoryview(bytearray(8)).cast("q")
        self.is_sell: bool = False

    @error_handler(set_status_code=True)
    def run_parsing_engine(self) -> None:
        while True:
            init_session: bool = False
            while True:
                if self.have_status():
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if self.task_status[0] & scs.COMPLETE:
                                self.final_actions()
                                self.set_proc_sc(scs.COMPLETE, wait_main_task=False)
                            return

                    elif task & scs.FP_RE_INIT:
                        self.writer.pre_re_init()
                        break

                if self.ds_wid[0] == self.ds_rid[0]:
                    self.alarm_clock()

                if self.ds_wid[0] != self.ds_rid[0]:
                    if self.get_trade_data():
                        if init_session is False:
                            self.writer.init_session(self.price[0], self.timestamp[0])
                            init_session = True

                        if self.writer.update_footprint(
                            self.price[0], self.qty[0], self.timestamp[0], self.is_sell
                        ):
                            self.update_success()
                            if self.writer.spare_flags[1] == 1:
                                self.writer.post_update()

                        self.post_update()

    def complete(self) -> bool:
        return self.ds_wid[0] == self.ds_rid[0]

    def final_actions(self) -> None:
        self.writer.wait_read_bbox()
        if not self.writer.bbox_is_read():
            if self.writer.copy_to():
                self.post_final_action()

        self.writer.wait_read_bbox()
        self.parsing_complete[0] = 1
        self.writer.final_actions()

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

        if (self.price[0] > 0) and (self.qty[0] > 0) and (self.timestamp[0] > 0):
            return True

        self.set_proc_sc(code=scs.UNVALID_DATA, wait_main_task=True)

        return False

    @abstractmethod
    def set_trade_data(self, raw_data: memoryview) -> None:
        pass

    @abstractmethod
    def update_success(self) -> None:
        pass

    @abstractmethod
    def post_update(self) -> None:
        pass
