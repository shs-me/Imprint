from abc import ABC, abstractmethod

from msgspec.json import Decoder

from ...utils.handlers import error_handler
from ...utils.monitoring.agent_manager import AgentManager
from ...utils.monitoring.status_codes import StatusCodes as scs
from .base_footprint_writer import FootprintWriter
from .utils.data_structs import AggTrade


class Parsing(ABC):
    def __init__(self, manager: AgentManager, writer: FootprintWriter) -> None:
        self.manager, self.writer = manager, writer

        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status, self.proc_status = manager.task_status, manager.proc_status

        cfgRaw = self.manager.cfgRaw
        self.decoder: Decoder[AggTrade] = Decoder(type=AggTrade, strict=False)
        self.data_size: int = cfgRaw.data_size
        self.data_offset: int = cfgRaw.data[0]
        self.dataHeader_offset: int = cfgRaw.dataHeader[0]
        self.cell_amount: int = cfgRaw.cell_amount
        self.wCellC: memoryview[int] = self.manager.raw_buf[
            slice(*cfgRaw.WriterCellCounter)
        ].cast("q")
        self.rCellC: memoryview[int] = self.manager.raw_buf[
            slice(*cfgRaw.ReaderCellCounter)
        ].cast("q")

        cfgMetrics = self.manager.cfgMetrics
        self.tradesParsed: memoryview = self.manager.metrics_buf[
            cfgMetrics.tradesParsed : cfgMetrics.tradesParsed + 1
        ]

        self.price: memoryview[float] = memoryview(bytearray(8)).cast("d")
        self.qty: memoryview[float] = memoryview(bytearray(8)).cast("d")
        self.timestamp: memoryview[int] = memoryview(bytearray(8)).cast("q")
        self.is_sell: bool = False

    @error_handler(set_status_code=True)
    def run_parsing_engine(self) -> None:
        # LocalLinks
        writer = self.writer
        proc_status, task_status = self.proc_status, self.task_status
        raw_buf = self.manager.raw_buf
        rCellC, wCellC = self.rCellC, self.wCellC
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount = self.cell_amount
        get_trade_data, alarm_clock = self.get_trade_data, self.alarm_clock
        update_success, post_update = self.update_success, self.post_update
        price, qty = self.price, self.qty
        timestamp, is_sell = self.timestamp, self.is_sell
        #  - - -
        while True:
            init_session: bool = False
            while True:
                if (proc_status[0] != 0) or (task_status[0] != 0):
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if task_status[0] & scs.COMPLETE:
                                self.final_actions()
                            return

                    elif task & scs.FP_RE_INIT:
                        writer.pre_re_init()
                        break

                alarm_clock()

                if get_trade_data(
                    raw_buf=raw_buf,
                    wCellC=wCellC,
                    rCellC=rCellC,
                    cell_amount=cell_amount,
                    data_size=data_size,
                    data_offset=data_offset,
                    dataHeader_offset=dataHeader_offset,
                ):
                    if init_session is False:
                        init_session = writer.init_session(price[0], timestamp[0])

                    if writer.update(price[0], qty[0], timestamp[0], is_sell):
                        update_success()

                    post_update()

    def complete(self) -> bool:
        return self.wCellC[0] == self.rCellC[0]

    def final_actions(self) -> None:
        self.writer.wait_read_space()
        if not self.writer.space_is_read():
            if self.writer.copy_to():
                self.post_final_action()

        self.writer.wait_read_space()
        self.tradesParsed[0] = 1
        self.writer.final_actions()
        self.set_proc_sc(scs.COMPLETE)

    @abstractmethod
    def post_final_action(self) -> None:
        pass

    @abstractmethod
    def alarm_clock(self) -> None:
        pass

    def get_trade_data(
        self,
        raw_buf: memoryview,
        wCellC: memoryview,
        rCellC: memoryview,
        cell_amount: int,
        data_size: int,
        data_offset: int,
        dataHeader_offset: int,
    ) -> bool:
        if wCellC[0] != rCellC[0]:
            cell: int = rCellC[0]
            lrd: int = raw_buf[cell + dataHeader_offset]
            start = cell * data_size + data_offset
            new_cell: int = cell + 1
            self.set_trade_data(raw_buf[start : start + lrd])
            rCellC[0] = new_cell if new_cell < cell_amount else 0

            if (self.price[0] > 0) and (self.qty[0] > 0) and (self.timestamp[0] > 0):
                return True

            self.set_proc_sc(code=scs.UNVALID_DATA)

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
