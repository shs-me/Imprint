import time
from multiprocessing.synchronize import Event

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
        wake_up_logic: Event,
        general_event: Event,
    ) -> None:
        self.manager: AgentManager = manager
        self.writer: FootprintWriter = writer
        self.pre_sleep_wss: Event = pre_sleep_wss
        self.wake_up_logic: Event = wake_up_logic
        self.wait_main: Event = general_event

        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status: memoryview = manager.task_status
        self.proc_status: memoryview = manager.proc_status

        self.decoder: Decoder[AggTrade] = Decoder(type=AggTrade, strict=False)
        self.backtesting = manager.backtesting
        self.btMode = manager.mode
        self.is_real: bool = self.btMode == bm.REAL_TIME_SIM
        self.is_zero_sleep: bool = self.btMode == bm.ZERO_SLEEP
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
        self.tradesParsed: memoryview = self.manager.metrics_buf[
            slice(*self.cfgMetrics.tradesParsed)
        ]

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
        get_trade_data, alarm_clock = self._get_trade_data, self._alarm_clock
        #  - - -
        while True:
            is_real: bool = self.is_real
            init_session: bool = False
            while True:
                if proc_status[0] != 0 or task_status[0] != 0:
                    task: bool | int = self.check_base_task(self.complete())
                    if isinstance(task, bool):
                        if task:
                            if task_status[0] & scs.COMPLETE:
                                self.final_actions(is_real)
                                pass
                            return

                    elif task & scs.FP_RE_INIT:
                        writer.pre_re_init()
                        break

                alarm_clock(task_status, RCellC, WCellC, pre_sleep_wss)
                if trade := get_trade_data(
                    raw_buf=raw_buf,
                    WCellC=WCellC,
                    RCellC=RCellC,
                    cell_amount=cell_amount,
                    data_size=data_size,
                    data_offset=data_offset,
                    dataHeader_offset=dataHeader_offset,
                    decoder=decoder,
                ):
                    if init_session is False:
                        init_session = writer.init_session(
                            price=trade.p, timestamp=trade.T
                        )
                    if writer.update(
                        price=trade.p,
                        qty=trade.q,
                        timestamp=trade.T,
                        is_sell=trade.m,
                    ):
                        if is_real:
                            wake_up_logic.set()

                    if is_real and (WCellC[0] == RCellC[0]):
                        pre_sleep_wss.clear()

    def complete(self) -> bool:
        return self.WriterCellCounter[0] == self.ReaderCellCounter[0]

    def final_actions(self, is_real: bool) -> None:
        self.writer.wait_read_space()
        if not self.writer.space_is_read():
            if self.writer.copy_to():
                if is_real:
                    self.wake_up_logic.set()

        self.writer.wait_read_space()
        self.tradesParsed[0] = 1
        self.writer.final_actions()
        self.set_proc_sc(scs.COMPLETE)

    def _alarm_clock(
        self,
        task_status: memoryview,
        RCellC: memoryview,
        WCellC: memoryview,
        pre_sleep_wss: Event,
    ) -> None:
        if not self.is_real:
            while WCellC[0] == RCellC[0]:
                if task_status[0] == 0:
                    if self.is_zero_sleep:
                        time.sleep(0)
                else:
                    return

        else:
            if WCellC[0] == RCellC[0]:
                pre_sleep_wss.wait()

    def _get_trade_data(
        self,
        raw_buf: memoryview,
        WCellC: memoryview,
        RCellC: memoryview,
        cell_amount: int,
        data_size: int,
        data_offset: int,
        dataHeader_offset: int,
        decoder: Decoder[AggTrade],
    ) -> None | AggTrade:
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

            return trade


@manager_office()
def run_parsing(
    parsing_event: Event,
    logic_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    writer: FootprintWriter = FootprintWriter(kwargs["manager"])
    agent: ParserAgent = ParserAgent(
        kwargs["manager"],
        writer=writer,
        wake_up_logic=logic_event,
        pre_sleep_wss=parsing_event,
        general_event=general_event,
    )
    agent.run_parsing_engine()
