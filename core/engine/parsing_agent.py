import gc
from multiprocessing.synchronize import Event

import msgspec
from msgspec.json import Decoder

from .. import AgentManager, error_handler, manager_office
from .. import StatusCodes as sc
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
        wake_up_logic: Event,
        general_event: Event,
    ) -> None:
        self.manager, self.writer = manager, writer
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.pre_sleep_wss, self.wake_up_logic = pre_sleep_wss, wake_up_logic
        self.wait_main: Event = general_event
        self.decoder: Decoder[AggTrade] = Decoder(type=AggTrade, strict=False)
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

    def _get_decode_raw_data(
        self,
        raw_buf: memoryview,
        RCellC: memoryview,
        cell_amount: int,
        data_size: int,
        data_offset: int,
        dataHeader_offset: int,
        decoder: Decoder[AggTrade],
    ) -> AggTrade | None:
        cell: int = RCellC[0]  # get cell where stopped
        lrd: int = raw_buf[cell + dataHeader_offset]  # get lrd from cell[header]
        start = cell * data_size + data_offset
        new_cell: int = cell + 1  # set cell for next parsing
        RCellC[0] = new_cell if new_cell < cell_amount else 0

        trade: AggTrade = decoder.decode(raw_buf[start : start + lrd])
        if trade.p < 0 or trade.q < 0 or trade.T < 0:
            self.set_status(code=sc.WARN1)
            return None
        else:
            return trade

    def _alarm_clock(
        self,
        tts: memoryview,
        RCellC: memoryview,
        WCellC: memoryview,
        cell_amount: int,
        safe_lag: int,
    ) -> bool:
        if ((WCellC[0] - RCellC[0] + cell_amount) % cell_amount) < safe_lag:
            counter = 1
            while WCellC[0] == RCellC[0]:
                counter += 1
                if counter >= tts[0]:
                    return True
            else:
                return False
        else:
            self.set_status(code=sc.WARN0)
            return False

    @error_handler(set_status_code=True)
    def run_parsing_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        decoder, writer = self.decoder, self.writer
        wake_up_logic, pre_sleep_wss = self.wake_up_logic, self.pre_sleep_wss
        set_status, have_problem = self.set_status, self.have_problem
        have_task = self.have_task
        raw_buf = self.manager.raw_buf
        tts_buf = self.manager.time_to_sleep_buf
        RCellC, WCellC = self.ReaderCellCounter, self.WriterCellCounter
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        safe_lag, cell_amount = self.safe_lag, self.cell_amount
        get_decode_raw_data, alarm_clock = self._get_decode_raw_data, self._alarm_clock
        #  - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            init_session = True
            while True:
                set_status(code=SLEEP)
                if have_problem() is False:
                    if have_task():
                        if wake_up_logic.is_set() is False:
                            wake_up_logic.set()
                        break

                    if alarm_clock(tts_buf, RCellC, WCellC, cell_amount, safe_lag):
                        pre_sleep_wss.clear()
                        pre_sleep_wss.wait()
                        continue

                    set_status(code=WAKE_UP)
                    if trade := get_decode_raw_data(
                        raw_buf=raw_buf,
                        RCellC=RCellC,
                        cell_amount=cell_amount,
                        data_size=data_size,
                        data_offset=data_offset,
                        dataHeader_offset=dataHeader_offset,
                        decoder=decoder,
                    ):
                        if init_session:
                            if writer.init_session(price=trade.p, timestamp=trade.T):
                                init_session = False
                            else:
                                continue

                        writer.update(
                            price=trade.p,
                            qty=trade.q,
                            timestamp=trade.T,
                            is_sell=trade.m,
                        )
                else:
                    return


@manager_office()
def run_parsing(
    parsing_event: Event,
    logic_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    writer: FootprintWriter = FootprintWriter(kwargs["manager"], guarantee=logic_event)
    agent: ParserAgent = ParserAgent(
        kwargs["manager"],
        writer=writer,
        wake_up_logic=logic_event,
        pre_sleep_wss=parsing_event,
        general_event=general_event,
    )
    agent.run_parsing_engine()
