import gc
from multiprocessing.synchronize import Event

import msgspec
from msgspec.json import Decoder

from ... import Config, ManagerAgent
from ... import StatusCodes as sc
from .. import error_action, manager_office
from . import FootprintWriter


class AggTrade(msgspec.Struct):
    T: int  # Trade time
    p: float  # Price
    q: float  # Quantity
    m: bool  # Is buyer maker?


class ParserAgent:
    def __init__(
        self,
        manager: ManagerAgent,
        writer: FootprintWriter,
        pre_sleep_wss: Event,
        wake_up_logic: Event,
        general_event: Event,
    ) -> None:
        __cfg, self.manager, self.writer = Config.ShmSharing, manager, writer
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.pre_sleep_wss, self.wake_up_logic = pre_sleep_wss, wake_up_logic
        self.wait_main: Event = general_event
        self.decoder: Decoder[AggTrade] = Decoder(type=AggTrade, strict=False)
        # InitGetRawData
        self.data_size, self.header_size = __cfg.Raw.data_size, __cfg.Raw.header_size
        self.data_offset: int = __cfg.Raw.data_offset[0]
        self.header_offset: int = __cfg.Raw.header_offset[0]
        self.cell_amount, self.safe_lag = __cfg.Raw.cell_amount, __cfg.Raw.safe_lag
        self.ncell_wr: memoryview[int] = self.manager.raw_buf[
            slice(*__cfg.Raw.ncell_offset)
        ].cast("q")

    def _get_decode_raw_data(
        self,
        raw_buf: memoryview,
        ncell_wr: memoryview,
        cell_amount: int,
        header_offset: int,
        data_size: int,
        data_offset: int,
        decoder: Decoder[AggTrade],
    ) -> AggTrade | None:
        ncell_r: int = ncell_wr[1]  # get cell where stopped
        lrd: int = raw_buf[ncell_r + header_offset]  # get lrd from cell[header]
        start = ncell_r * data_size + data_offset
        ncell_r_new: int = ncell_r + 1  # set cell for next parsing
        ncell_wr[1] = ncell_r_new if ncell_r_new < cell_amount else 0
        trade: AggTrade = decoder.decode(raw_buf[start : start + lrd])
        if trade.p < 0 or trade.q < 0 or trade.T < 0:
            self.set_status(code=sc.WARN1)
            return None
        else:
            return trade

    def _alarm_clock(
        self, tts: memoryview, ncells: memoryview, acell: int, slag: int
    ) -> bool:
        if (ncells[0] - ncells[1] + acell) % acell < slag:
            counter = 1
            while ncells[0] == ncells[1]:
                counter += 1
                if counter >= tts[0]:
                    return True
            else:
                return False
        else:
            self.set_status(code=sc.WARN0)
            return False

    @error_action(set_sc=True)
    def run_parsing_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        decoder, writer = self.decoder, self.writer
        wake_up_logic, pre_sleep_wss = self.wake_up_logic, self.pre_sleep_wss
        set_status, have_problem = self.set_status, self.have_problem
        have_task = self.have_task
        tts_buf = self.manager.time_to_sleep_buf
        raw_buf, ncells = self.manager.raw_buf, self.ncell_wr
        data_size, data_offset = self.data_size, self.data_offset
        header_offset, slag, acell = self.header_offset, self.safe_lag, self.cell_amount
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

                    if alarm_clock(tts=tts_buf, ncells=ncells, acell=acell, slag=slag):
                        pre_sleep_wss.clear()
                        pre_sleep_wss.wait()
                        continue

                    set_status(code=WAKE_UP)
                    if trade := get_decode_raw_data(
                        raw_buf=raw_buf,
                        ncell_wr=ncells,
                        cell_amount=acell,
                        header_offset=header_offset,
                        data_size=data_size,
                        data_offset=data_offset,
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


@manager_office(head_of_office=False)
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
