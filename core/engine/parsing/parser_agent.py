import gc
from multiprocessing.synchronize import Event, Semaphore

import msgspec
from msgspec.json import Decoder

from ... import Config, MonitorObj
from ... import StatusCodes as sc
from .. import error_action, shm_manager
from . import GridWriter


class AggTrade(msgspec.Struct):
    T: int  # Trade time
    p: float  # Price
    q: float  # Quantity
    m: bool  # Is buyer maker?


class ParserAgent:
    def __init__(
        self,
        mo: MonitorObj,
        writer: GridWriter,
        pre_sleep_wss: Event,
        wake_up_logic: Event,
        general_event: Event,
    ) -> None:
        __cfg, self._mo, self.writer = Config.CoreConfig, mo, writer
        self.id_m, self.have_watchdog_task = self._mo.id_m, self._mo.have_watchdog_task
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.pre_sleep_wss, self.wake_up_logic = pre_sleep_wss, wake_up_logic
        self.wait_main: Event = general_event
        self.decoder: Decoder[AggTrade] = Decoder(type=AggTrade, strict=False)
        # InitGetRawData
        self.data_size, self.header_size = __cfg.Raw.data_size, __cfg.Raw.header_size
        self.data_offset: int = __cfg.Raw.data_offset[0]
        self.header_offset: int = __cfg.Raw.header_offset[0]
        self.cell_amount, self.safe_lag = __cfg.Raw.cell_amount, __cfg.Raw.safe_lag
        self.ncell_wr: memoryview[int] = self._mo.raw_buf[
            slice(*__cfg.Raw.ncell_offset)
        ].cast("q")

    def _get_raw_data(
        self,
        raw_buf: memoryview,
        ncell_wr: memoryview,
        cell_amount: int,
        header_offset: int,
        data_size: int,
        data_offset: int,
    ) -> memoryview | None:
        """
        Get RawData[JSON Bytes] from RawSHM.\n
        ncell_wr: number cell writer & reader
        """
        ncell_r: int = ncell_wr[1]  # get cell where stopped
        lrd: int = raw_buf[ncell_r + header_offset]  # get lrd from cell[header]
        start = ncell_r * data_size + data_offset
        raw_data: memoryview = raw_buf[start : start + lrd]  # get mview cell[data]
        ncell_r_new: int = ncell_r + 1  # set cell for next parsing
        ncell_wr[1] = ncell_r_new if ncell_r_new < cell_amount else 0
        return raw_data

    def _decode_raw_data(
        self, raw_data: memoryview, decoder: Decoder[AggTrade]
    ) -> AggTrade | None:
        """Decode RawData[JSON] to Struct AggTrade"""
        trade: AggTrade = decoder.decode(raw_data)
        if trade.p < 0 or trade.q < 0 or trade.T < 0:
            self.set_status(id_m=self.id_m, code=sc.WARN1)
            return None

        return trade

    def _alarm_clock(self, ncells, acell, slag) -> bool:
        ncell_w, ncell_r = ncells[0], ncells[1]
        if ((ncell_w - ncell_r + acell) % acell) < slag:
            if ncell_r == ncell_w:
                return True

            else:
                return False
        else:
            self.set_status(id_m=self.id_m, code=sc.WARN0)
            return False

    @error_action(set_sc_code=True)
    def run_parsing_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        decoder, writer, raw_buf = self.decoder, self.writer, self._mo.raw_buf
        id_m, set_status, have_problem = self.id_m, self.set_status, self.have_problem
        data_size = self.data_size
        data_offset, header_offset = self.data_offset, self.header_offset
        slag, ncells, acell = self.safe_lag, self.ncell_wr, self.cell_amount
        wake_up_logic, pre_sleep_wss = self.wake_up_logic, self.pre_sleep_wss
        get_raw_data, decode_raw_data = self._get_raw_data, self._decode_raw_data
        alarm_clock, have_watchdog_task = self._alarm_clock, self.have_watchdog_task
        #  - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            while True:
                set_status(id_m=id_m, code=SLEEP)
                if have_problem() is False:
                    if have_watchdog_task():
                        if wake_up_logic.is_set() is False:
                            wake_up_logic.set()
                            break

                    if alarm_clock(ncells=ncells, acell=acell, slag=slag):
                        pre_sleep_wss.clear()
                        pre_sleep_wss.wait()
                        continue

                    set_status(id_m=id_m, code=WAKE_UP)
                    if raw_data := get_raw_data(
                        raw_buf=raw_buf,
                        ncell_wr=ncells,
                        cell_amount=acell,
                        header_offset=header_offset,
                        data_size=data_size,
                        data_offset=data_offset,
                    ):
                        if trade := decode_raw_data(raw_data=raw_data, decoder=decoder):
                            writer.update(
                                price=trade.p,
                                qty=trade.q,
                                timestamp=trade.T,
                                is_sell=trade.m,
                            )
                else:
                    return


@shm_manager(create=False)
def run_parsing(
    pre_sleep_wss: Event,
    wake_up_logic: Event,
    parser_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
    shm_buf: memoryview,
) -> None:
    gc.disable()
    mo: MonitorObj = MonitorObj(
        shm_buf=shm_buf,
        proc_name=Config.CoreConfig.Status.parsing.__name__,
        warn_error_status=warn_error_status,
        monitor=parser_monitor,
    )

    writer: GridWriter = GridWriter(mo=mo, guarantee=wake_up_logic)
    agent: ParserAgent = ParserAgent(
        mo=mo,
        writer=writer,
        wake_up_logic=wake_up_logic,
        pre_sleep_wss=pre_sleep_wss,
        general_event=general_event,
    )
    agent.run_parsing_engine()
    gc.collect()
