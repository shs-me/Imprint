import gc
import sys
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
        sem_sleep_parsing: Semaphore,
        sleep_logic: Event,
        general_event: Event,
    ) -> None:
        # Initialization
        core_cfg = Config.CoreConfig()
        self._mo = mo
        self._id_m_ = self._mo._id_m
        self._set, self._get = self._mo.set_, self._mo.get_
        self.acquire_wss = sem_sleep_parsing
        self.sleep_logic = sleep_logic
        self.wait_main = general_event
        # variables
        self.decoder = msgspec.json.Decoder(type=AggTrade, strict=False)
        # RawSHM.buf
        self.raw_buf = self._mo.shms[core_cfg.Raw.__name__]["buf"]
        # MetricsSHM.buf
        self.metrics_buf = self._mo.shms[core_cfg.Metrics.__name__]["buf"]
        # InitGetRawData
        self.cell_amount = core_cfg.Raw.cell_amount
        self.data_size = core_cfg.Raw.data_size
        self.header_size = core_cfg.Raw.header_size
        self.flag = core_cfg.Raw.flag - 1
        self.flag_start = self.flag - 1

    @staticmethod
    def create(
        sem_sleep_parsing: Semaphore,
        sleep_logic: Event,
        parser_monitor: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.parsing.__name__,
                warn_error_status=warn_error_status,
                _monitor=parser_monitor,
            )

            return ParserAgent(
                mo=mo,
                sleep_logic=sleep_logic,
                sem_sleep_parsing=sem_sleep_parsing,
                general_event=general_event,
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    def _get_raw_data(
        self,
        flag: int,
        cell_amount: int,
        header_size: int,
        id_m: int,
        set_status,
        raw_buf: memoryview,
    ) -> memoryview | bool:
        """Get RawData[JSON] from RawSHM"""
        try:
            iro = raw_buf[flag]  # iro: Index Read Old
            if (iro + 1) >= (cell_amount * header_size):
                irn = raw_buf[flag] = header_size
                iro = 0
            else:
                irn = raw_buf[flag] = iro + header_size  # irn: Index Read New

            lrd = raw_buf[iro]  # Get Len Raw Data
            raw_data = raw_buf[
                (irn * cell_amount) : ((irn * cell_amount) + lrd)
            ]  # Get Raw Data
            return raw_data

        except Exception:
            traceback.print_exc()
            set_status(id_m, 154)
            return False

    def _decode_raw_data(
        self, raw_data: memoryview, decoder, id_m_: int, set_status
    ) -> AggTrade | bool | None:
        """Decode RawData[JSON] to Struct AggTrade"""
        try:
            trade = decoder(raw_data)
            if trade.p < 0 or trade.q < 0 or trade.T < 0:
                return None

            return trade

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m_, 153)
            return False

    def run_parsing_engine(self) -> None:
        # LocalLinks
        _raw_buf, _metrics_buf = self.raw_buf, self.metrics_buf  # ShM.Buf's
        _decoder = self.decoder.decode  # Msgspec Json Decoder
        # MonitorObj
        _id_m, set_status, get_status = self._id_m_, self._set, self._get
        # GetRawData
        _cell_amount, _header_size = self.cell_amount, self.header_size
        _flag, _flag_start = self.flag, self.flag_start
        # Semaphore, Event
        _sleep_logic, _acquire_wss = self.sleep_logic, self.acquire_wss
        # Methods
        get_raw_data = self._get_raw_data
        decode_raw_data = self._decode_raw_data
        #  - - -
        try:
            engine = GridEngine.create(_mo_=self._mo)
            if isinstance(engine, GridEngine):
                while True:
                    try:
                        gc.collect()
                        self.wait_main.wait()
                        if _raw_buf[_flag_start] != 1:
                            while _acquire_wss.acquire(block=False):
                                pass

                            _raw_buf[_flag] = _raw_buf[_flag + 1]
                            _raw_buf[_flag_start] = 1

                        while True:
                            if get_status(_id_m) is not True:
                                set_status(_id_m, 4)  # IDLE # TIME START
                                _acquire_wss.acquire()
                                if get_status(_id_m, proc=True):
                                    _sleep_logic.wait()
                                    break

                                set_status(_id_m, 5)  # Running # TIME WAKE_UP
                                if isinstance(
                                    (
                                        raw_data := get_raw_data(
                                            flag=_flag,
                                            cell_amount=_cell_amount,
                                            header_size=_header_size,
                                            id_m=_id_m,
                                            set_status=set_status,
                                            raw_buf=_raw_buf,
                                        )
                                    ),
                                    memoryview,
                                ):
                                    if isinstance(
                                        (
                                            trade := decode_raw_data(
                                                raw_data=raw_data,
                                                decoder=_decoder,
                                                id_m_=_id_m,
                                                set_status=set_status,
                                            )
                                        ),
                                        AggTrade,
                                    ):
                                        if engine.update(
                                            price=trade.p,
                                            qty=trade.q,
                                            timestamp=trade.T,
                                            is_sell=trade.m,
                                        ):
                                            _sleep_logic.set()

                                    elif trade is False:
                                        sys.exit()

                                elif raw_data is False:
                                    sys.exit()

                            else:
                                sys.exit()

                    except Exception:
                        traceback.print_exc()  # Debug
                        set_status(_id_m, 150)  # Error in this func
                        break
            else:
                set_status(_id_m, 151)  # Error in engine
                return

        except Exception:
            traceback.print_exc()  # Debug
            set_status(_id_m, 150)  # Error in this func


def run_parsing(
    sem_sleep_parsing: Semaphore,
    sleep_logic: Event,
    parser_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    agent = ParserAgent.create(
        sem_sleep_parsing=sem_sleep_parsing,
        sleep_logic=sleep_logic,
        parser_monitor=parser_monitor,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, ParserAgent):
        agent.run_parsing_engine()
