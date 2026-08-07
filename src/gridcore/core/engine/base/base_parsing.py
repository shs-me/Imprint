"""Data parsing engine processing raw tick ring buffers into Footprint updates."""

from abc import ABC, abstractmethod

from ...settings import StatusCodes as scs
from ...utils.handlers import error_handler
from ...utils.monitoring.agent_manager import AgentManager
from .base_footprint_writer import FootprintWriter


class Parsing(ABC):
    """Base class managing tick stream ring buffer ingestion and FootprintWriter dispatch."""

    def __init__(self, manager: AgentManager, writer: FootprintWriter) -> None:
        self.manager: AgentManager = manager
        self.set_proc_sc = manager.set_proc_sc
        self.have_status = manager.have_status
        self.task_status = manager.task_status
        self.check_base_task = manager.check_base_task

        self.writer: FootprintWriter = writer

        cfgDS = self.manager.cfgDataStream
        self.cell_amount: int = cfgDS.cell_amount
        self.data_size: int = cfgDS.data_size
        self.data: memoryview = cfgDS.data
        self.data_header: memoryview = cfgDS.data_header
        self.wCellC: memoryview = cfgDS.writer_id.cast("q")
        self.rCellC: memoryview = cfgDS.reader_id.cast("q")

        cfgMetrics = self.manager.cfgMetrics
        self.parsing_complete: memoryview = cfgMetrics.parsing_complete

        self.price: memoryview[float] = memoryview(bytearray(8)).cast("d")
        self.qty: memoryview[float] = memoryview(bytearray(8)).cast("d")
        self.timestamp: memoryview = memoryview(bytearray(8)).cast("q")
        self.is_sell: bool = False

    @error_handler(set_status_code=True)
    def run_parsing_engine(self) -> None:
        """Main loop consuming DataStream ring buffer cells and updating FootprintWriter."""

        # LocalLinks
        writer = self.writer
        have_status, task_status = self.have_status, self.task_status
        rCellC, wCellC = self.rCellC, self.wCellC
        data, data_size = self.data, self.data_size
        data_header = self.data_header
        cell_amount = self.cell_amount
        get_trade_data, alarm_clock = self.get_trade_data, self.alarm_clock
        update_success, post_update = self.update_success, self.post_update
        price, qty = self.price, self.qty
        timestamp = self.timestamp
        #  - - -
        while True:
            init_session: bool = False
            while True:
                if have_status():
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if task_status[0] & scs.COMPLETE:
                                self.final_actions()
                                self.set_proc_sc(scs.COMPLETE)
                            return

                    elif task & scs.FP_RE_INIT:
                        writer.pre_re_init()
                        break

                alarm_clock()

                if get_trade_data(
                    data=data,
                    data_header=data_header,
                    wCellC=wCellC,
                    rCellC=rCellC,
                    cell_amount=cell_amount,
                    data_size=data_size,
                ):
                    if init_session is False:
                        writer.init_session(price[0], timestamp[0])
                        init_session = True

                    if writer.update_footprint(
                        price[0], qty[0], timestamp[0], self.is_sell
                    ):
                        update_success()

                    post_update()

    def complete(self) -> bool:
        """Checks if DataStream ring buffer reader has caught up to writer head position."""

        return self.wCellC[0] == self.rCellC[0]

    def final_actions(self) -> None:
        """Flushes remaining pending updates to shared memory and sets parsing completion flag."""

        self.writer.wait_read_space()
        if not self.writer.space_is_read():
            if self.writer.copy_to():
                self.post_final_action()

        self.writer.wait_read_space()
        self.parsing_complete[0] = 1
        self.writer.final_actions()

    @abstractmethod
    def post_final_action(self) -> None:
        """Abstract teardown hook invoked upon parsing pipeline termination."""

        pass

    @abstractmethod
    def alarm_clock(self) -> None:
        """Abstract idle wait hook invoked when DataStream ring buffer is empty."""

        pass

    def get_trade_data(
        self,
        data: memoryview,
        data_header: memoryview,
        wCellC: memoryview,
        rCellC: memoryview,
        cell_amount: int,
        data_size: int,
    ) -> bool:
        """Extracts raw tick buffer from DataStream cell and advances reader head position.

        Returns:
            bool: True if trade payload contains valid price, quantity, and timestamp parameters.
        """

        if wCellC[0] != rCellC[0]:
            cell: int = rCellC[0]
            lrd: int = data_header[cell]
            start: int = cell * data_size
            new_cell: int = cell + 1
            self.set_trade_data(data[start : start + lrd])
            rCellC[0] = new_cell if new_cell < cell_amount else 0

            if (self.price[0] > 0) and (self.qty[0] > 0) and (self.timestamp[0] > 0):
                return True

            self.set_proc_sc(code=scs.UNVALID_DATA)

        return False

    @abstractmethod
    def set_trade_data(self, raw_data: memoryview) -> None:
        """Abstract binary unpacking hook deserializing raw stream cell payload into tick values."""

        pass

    @abstractmethod
    def update_success(self) -> None:
        """Abstract callback invoked following a successful Footprint update."""

        pass

    @abstractmethod
    def post_update(self) -> None:
        """Abstract callback invoked after processing each tick iteration."""

        pass
