import gc
import time
from multiprocessing.synchronize import Event, Lock

import msgspec
from msgspec.json import Decoder

from .. import AgentManager, error_handler, manager_office
from .. import StatusCodes as sc
from ..settings import BacktestingMode as bm
from . import FootprintWriter


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
        self.manager, self.writer = manager, writer
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.pre_sleep_wss, self.wake_up_logic = pre_sleep_wss, wake_up_logic
        self.wait_main: Event = general_event
        self.decoder: Decoder[AggTrade] = Decoder(type=AggTrade, strict=False)
        self.mode = manager.cfgBacktesting.mode
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

    @error_handler(set_status_code=True)
    def run_parsing_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        decoder, writer = self.decoder, self.writer
        pre_sleep_wss, wake_up_logic = self.pre_sleep_wss, self.wake_up_logic
        set_status, have_problem = self.set_status, self.have_problem
        have_task, status_task = self.have_task, self.manager.status_task
        raw_buf = self.manager.raw_buf
        RCellC, WCellC = self.ReaderCellCounter, self.WriterCellCounter
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount = self.cell_amount
        update_cells, alarm_clock = self._update_cells, self._alarm_clock
        #  - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            self.init_session = True
            while True:
                set_status(code=SLEEP)
                if have_problem() is False:
                    if have_task():
                        break

                    alarm_clock(status_task, RCellC, WCellC, pre_sleep_wss)
                    set_status(code=WAKE_UP)
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

                else:
                    return

    def _alarm_clock(
        self,
        status_task: memoryview,
        RCellC: memoryview,
        WCellC: memoryview,
        pre_sleep_wss: Event,
    ) -> None:
        if self.mode == bm.NONE_STOP:
            while WCellC[0] == RCellC[0] and status_task[0] == 0:
                pass

        elif self.mode == bm.ZERO_SLEEP:
            while WCellC[0] == RCellC[0] and status_task[0] == 0:
                time.sleep(0)

        elif self.mode == bm.REAL_TIME_SIM:
            pre_sleep_wss.clear()
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
        while WCellC[0] != RCellC[0]:
            cell: int = RCellC[0]
            lrd: int = raw_buf[cell + dataHeader_offset]
            start = cell * data_size + data_offset
            new_cell: int = cell + 1
            RCellC[0] = new_cell if new_cell < cell_amount else 0
            trade: AggTrade = decoder.decode(raw_buf[start : start + lrd])
            if trade.p < 0 or trade.q < 0 or trade.T < 0:
                self.set_status(code=sc.WARN1)
                break
            else:
                if self.init_session:
                    if writer.init_session(price=trade.p, timestamp=trade.T):
                        self.init_session = False
                    else:
                        break

                temp = writer.update(
                    price=trade.p,
                    qty=trade.q,
                    timestamp=trade.T,
                    is_sell=trade.m,
                )
                if temp is False:
                    pass
                elif temp is True:
                    if self.mode == bm.REAL_TIME_SIM:
                        wake_up_logic.release()
                elif temp is None:
                    break


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
