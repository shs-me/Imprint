import time
from multiprocessing.synchronize import Event, Lock

import msgspec
from msgspec.json import Decoder

from core.engine.agents_utils.parsing.footprint_writer import FootprintWriter
from core.settings import BacktestingMode as bm
from core.utils.handlers import error_handler
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office
from core.utils.monitoring.status_codes import StatusCodes as scs


class AggTrade(msgspec.Struct):
    T: int  # Trade time
    p: float  # Price
    q: float  # Quantity
    m: bool  # Is buyer maker?


class ParserAgent:
    def __init__(
        self,
        manager: AgentManager,
        writer: FootprintWriter,
        pre_sleep_wss: Event,
        wake_up_logic: Lock,
        general_event: Event,
    ) -> None:
        self.manager: AgentManager = manager
        self.writer: FootprintWriter = writer
        self.pre_sleep_wss: Event = pre_sleep_wss
        self.wake_up_logic: Lock = wake_up_logic
        self.wait_main: Event = general_event

        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status: memoryview = manager.task_status
        self.proc_status: memoryview = manager.proc_status

        self.decoder: Decoder[AggTrade] = Decoder(type=AggTrade, strict=False)
        self.backtesting = manager.backtesting
        self.btMode = manager.mode
        # InitGetRawData
        self.cfgRaw = self.manager.cfgRaw
        self.data_size = self.cfgRaw.data_size
        self.header_size = self.cfgRaw.header_size
        self.data_offset: int = self.cfgRaw.data[0]
        self.dataHeader_offset: int = self.cfgRaw.dataHeader[0]
        self.cell_amount = self.cfgRaw.cell_amount
        self.safe_lag = self.cfgRaw.safe_lag
        self.WriterCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.WriterCellCounter)
        ].cast("q")
        self.ReaderCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.ReaderCellCounter)
        ].cast("q")
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.timeStartReading = self.manager.metrics_buf[
            slice(*self.cfgMetrics.timeStartReading)
        ].cast("q")

    @error_handler(set_status_code=True)
    def run_parsing_engine(self) -> None:
        # LocalLinks
        pre_sleep_wss, wake_up_logic = self.pre_sleep_wss, self.wake_up_logic
        decoder, writer = self.decoder, self.writer
        # - - -
        proc_status, task_status = self.proc_status, self.task_status
        # - - -
        raw_buf = self.manager.raw_buf
        RCellC, WCellC = self.ReaderCellCounter, self.WriterCellCounter
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount = self.cell_amount
        # - - -
        update_cells, alarm_clock = self._update_cells, self._alarm_clock
        #  - - -
        while True:
            self.init_session = True
            while True:
                if proc_status[0] != 0 or task_status[0] != 0:
                    task: bool | int = self.check_base_task(complete=self.complete())
                    if isinstance(task, bool):
                        if task:
                            return

                    elif task & scs.FP_RE_INIT:
                        writer.pre_re_init()
                        break

                alarm_clock(task_status, RCellC, WCellC, pre_sleep_wss)
                update_cells(
                    raw_buf=raw_buf,
                    WCellC=WCellC,
                    RCellC=RCellC,
                    cell_amount=cell_amount,
                    data_size=data_size,
                    data_offset=data_offset,
                    dataHeader_offset=dataHeader_offset,
                    decoder=decoder,
                    writer=writer,
                    wake_up_logic=wake_up_logic,
                )

    def complete(self) -> bool:
        return self.WriterCellCounter[0] == self.ReaderCellCounter[0]

    def _alarm_clock(
        self,
        task_status: memoryview,
        RCellC: memoryview,
        WCellC: memoryview,
        pre_sleep_wss: Event,
    ) -> None:
        if self.backtesting:
            mode, ZERO_SLEEP = self.btMode, bm.ZERO_SLEEP
            if mode == bm.NONE_STOP or mode == ZERO_SLEEP:
                while WCellC[0] == RCellC[0] and task_status[0] == 0:
                    if mode == ZERO_SLEEP:
                        time.sleep(0)
                return

        if WCellC[0] == RCellC[0] and task_status[0] == 0:
            pre_sleep_wss.clear()
            if WCellC[0] == RCellC[0] and task_status[0] == 0:
                pre_sleep_wss.wait()

    def _update_cells(
        self,
        raw_buf: memoryview,
        WCellC: memoryview,
        RCellC: memoryview,
        cell_amount: int,
        data_size: int,
        data_offset: int,
        dataHeader_offset: int,
        decoder: Decoder[AggTrade],
        writer: FootprintWriter,
        wake_up_logic: Lock,
    ) -> None:
        if WCellC[0] != RCellC[0]:
            cell: int = RCellC[0]
            lrd: int = raw_buf[cell + dataHeader_offset]
            start = cell * data_size + data_offset
            new_cell: int = cell + 1
            RCellC[0] = new_cell if new_cell < cell_amount else 0
            trade: AggTrade = decoder.decode(raw_buf[start : start + lrd])
            if trade.p < 0 or trade.q < 0 or trade.T < 0:
                self.set_proc_sc(code=scs.UNVALID_DATA)
                return
            else:
                if self.init_session:
                    if writer.init_session(price=trade.p, timestamp=trade.T):
                        self.init_session = False
                    else:
                        return

                if writer.update(
                    price=trade.p,
                    qty=trade.q,
                    timestamp=trade.T,
                    is_sell=trade.m,
                ):
                    self.timeStartReading[0] = time.perf_counter_ns()
                    if self.backtesting and self.btMode != bm.REAL_TIME_SIM:
                        return

                    wake_up_logic.release()


@manager_office()
def run_parsing(
    parsing_event: Event,
    logic_lock: Lock,
    general_event: Event,
    **kwargs,
) -> None:
    writer: FootprintWriter = FootprintWriter(kwargs["manager"], guarantee=logic_lock)
    agent: ParserAgent = ParserAgent(
        kwargs["manager"],
        writer=writer,
        wake_up_logic=logic_lock,
        pre_sleep_wss=parsing_event,
        general_event=general_event,
    )
    agent.run_parsing_engine()
