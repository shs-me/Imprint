import gc
import traceback
from multiprocessing.synchronize import Event, Semaphore

import msgspec

from ... import Config, MonitorObj
from . import GridEngine


class AggTrade(msgspec.Struct):
    T: int  # Trade time
    p: float  # Price
    q: float  # Quantity
    m: bool  # Is buyer maker?


class ParserAgent:
    def __init__(
        self,
        mo: MonitorObj,
        engine: GridEngine,
        pre_sleep_wss: Event,
        wake_up_logic: Event,
        general_event: Event,
    ) -> None:
        __cfg, self._mo, self.engine = Config.CoreConfig, mo, engine
        self._set, self._get, self.id_m = self._mo.set_, self._mo.get_, self._mo.id_m
        self.pre_sleep_wss, self.wake_up_logic = pre_sleep_wss, wake_up_logic
        self.wait_main = general_event
        self.decoder = msgspec.json.Decoder(type=AggTrade, strict=False)
        # InitGetRawData
        self.data_size, self.header_size = __cfg.Raw.data_size, __cfg.Raw.header_size
        self.data_offset = __cfg.Raw.data_offset[0]
        self.header_offset = __cfg.Raw.header_offset[0]
        self.cell_amount = __cfg.Raw.cell_amount
        # SHM.buf
        self.raw_buf = self._mo.shms[__cfg.Raw.__name__]["buf"]
        self.ncell_wr = self.raw_buf[
            __cfg.Raw.ncell_offset[0] : __cfg.Raw.ncell_offset[1]
        ].cast("q")

    def _get_raw_data(
        self,
        raw_buf: memoryview,
        ncell_wr: memoryview,
        cell_amount: int,
        header_size: int,
        header_offset: int,
        data_size: int,
        data_offset: int,
    ) -> memoryview | None:
        """
        Get RawData[JSON Bytes] from RawSHM.\n
        ncell_wr: number cell writer & reader
        """
        try:
            ncell_r: int = ncell_wr[1]
            lrd = raw_buf[ncell_r + header_offset]
            start = ncell_r * data_size + data_offset
            raw_data = raw_buf[start : start + lrd]
            ncell_wr[1] = (
                ncell_w if (ncell_w := ncell_r + header_size) < cell_amount else 0
            )
            return raw_data

        except Exception:
            traceback.print_exc()
            self._set(self.id_m, 154)
            return None

    def _decode_raw_data(
        self,
        raw_data: memoryview,
        decoder: msgspec.json.Decoder[AggTrade],
    ) -> AggTrade | None:
        """Decode RawData[JSON] to Struct AggTrade"""
        try:
            trade = decoder.decode(raw_data)
            if trade.p < 0 or trade.q < 0 or trade.T < 0:
                self._set(self.id_m, 60)
                return None

            return trade

        except Exception:
            traceback.print_exc()  # Debug
            self._set(self.id_m, 153)
            return None

    def run_parsing_engine(self) -> None:
        # LocalLinks
        decoder, engine = self.decoder, self.engine
        id_m, set_status, get_status = self.id_m, self._set, self._get
        header_size, data_size = self.header_size, self.data_size
        data_offset, header_offset = self.data_offset, self.header_offset
        raw_buf, ncell_wr, cell_amount = self.raw_buf, self.ncell_wr, self.cell_amount
        wake_up_logic, pre_sleep_wss = self.wake_up_logic, self.pre_sleep_wss
        get_raw_data, decode_raw_data = self._get_raw_data, self._decode_raw_data
        #  - - -
        try:
            while True:
                try:
                    gc.collect()
                    self.wait_main.wait()
                    while True:
                        if get_status(id_m) is not True:
                            set_status(id_m, 4)  # IDLE # TIME START
                            if ncell_wr[1] == ncell_wr[0]:
                                pre_sleep_wss.clear()
                                pre_sleep_wss.wait()

                            if get_status(id_m, proc=True):
                                if wake_up_logic.is_set() is False:
                                    wake_up_logic.set()
                                    break

                            set_status(id_m, 5)  # Running # TIME WAKE_UP
                            if raw_data := get_raw_data(
                                raw_buf=raw_buf,
                                ncell_wr=ncell_wr,
                                cell_amount=cell_amount,
                                header_size=header_size,
                                header_offset=header_offset,
                                data_size=data_size,
                                data_offset=data_offset,
                            ):
                                if trade := decode_raw_data(
                                    raw_data=raw_data, decoder=decoder
                                ):
                                    engine.update(
                                        price=trade.p,
                                        qty=trade.q,
                                        timestamp=trade.T,
                                        is_sell=trade.m,
                                    )
                        else:
                            return

                except Exception:
                    traceback.print_exc()  # Debug
                    set_status(id_m, 150)  # Error in this func
                    break

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m, 150)  # Error in this func


def run_parsing(
    pre_sleep_wss: Event,
    wake_up_logic: Event,
    parser_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    try:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.parsing.__name__,
                warn_error_status=warn_error_status,
                _monitor=parser_monitor,
            )
        except Exception:
            return

        engine = GridEngine.create(_mo_=mo, guarantee=wake_up_logic)
        if isinstance(engine, GridEngine):
            agent = ParserAgent(
                mo=mo,
                engine=engine,
                wake_up_logic=wake_up_logic,
                pre_sleep_wss=pre_sleep_wss,
                general_event=general_event,
            )
            agent.run_parsing_engine()
            agent, engine = None, None
            gc.collect()

        else:
            mo.set_(mo.id_m, 151)

    finally:
        gc.collect()
