import gc
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

import msgspec

from .. import MonitorObj
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
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        sleep_logic: Event,
        general_event: Event,
        writer_sleep: Event,
    ) -> None:
        # initialization
        self._mo = mo
        self._get, self._set, self._id_m_ = (
            self._mo.get_,
            self._mo.set_,
            self._mo._status(daughter=False),
        )

        self.cfg = cfg
        self.acquire_wss = sem_sleep_parsing
        self.sleep_logic = sleep_logic
        self.wait_main = general_event
        self.wait_reader = writer_sleep
        # variables
        self.decoder = msgspec.json.Decoder(type=AggTrade, strict=False)
        # RawSHM.buf
        self.raw_buf = self._mo.shms["raw"]["buf"]
        # MetricsSHM.buf
        self.metrics_buf = self._mo.shms["metrics"]["buf"]
        # InitGetRawData
        self.ac = self.cfg["raw"]["ac"]  # Amount Cells
        self.dsib = self.cfg["raw"]["dsib"]  # Data size in bytes
        self.hsib = self.cfg["raw"]["hsib"]  # Headers size in bytes
        self._ir = self._mo.shms["raw"]["shm"].size - 2  # Index, Write counter
        self._sssd = self._mo.shms["raw"]["shm"].size - 3  # Index, Start Start Set Data

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        sleep_logic: Event,
        parser_monitor: Semaphore,
        general_event: Event,
        writer_sleep: Event,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            # Init SHM, profilingArray, StatusSHM
            mo = MonitorObj(
                proc_name="parsing",
                config=cfg,
                warn_error_status=warn_error_status,
                _monitor=parser_monitor,
            )

            return ParserAgent(
                mo=mo,
                cfg=cfg,
                sleep_logic=sleep_logic,
                sem_sleep_parsing=sem_sleep_parsing,
                general_event=general_event,
                writer_sleep=writer_sleep,
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    # Get Bytes from RawSHM
    def _get_raw_data(
        self,
        ir: int,
        ac: int,
        hsib: int,
        _id_m_,
        _set_status,
        _raw_buf: memoryview,
    ) -> memoryview | bool:
        try:
            iro = _raw_buf[ir]  # iro: Index Read Old
            if (iro + 1) >= (ac * hsib):  # ac: Amount Cells
                irn = _raw_buf[ir] = hsib  # hsib: Header Size In Byte
                iro = 0
            else:
                irn = _raw_buf[ir] = hsib + iro  # irn: Index Read New

            lrd = _raw_buf[iro]  # Get Len Raw Data
            raw_data = _raw_buf[(irn * ac) : ((irn * ac) + lrd)]  # Get Raw Data
            return raw_data

        except Exception:
            traceback.print_exc()
            _set_status(_id_m_, 154)
            return False

    # Decode RawData to Struct AggTrade
    def _decode_raw_data(
        self,
        _id_m_,
        decoder,
        _set_status,
        raw_data: memoryview | None,
    ) -> AggTrade | bool | None:
        try:
            if raw_data is None:
                return None

            trade = decoder(raw_data)
            if trade.p < 0 or trade.q < 0 or trade.T < 0:
                return None

            return trade

        except Exception:
            traceback.print_exc()  # Debug
            _set_status(_id_m_, 153)
            return False

    def run_parsing_engine(
        self,
    ) -> None:
        # JSON Decoder, SHM.Buf - LocalLink
        _raw_buf, _metrics_buf, _decoder = (
            self.raw_buf,
            self.metrics_buf,
            self.decoder.decode,
        )
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = (
            self._id_m_,
            self._set,
            self._get,
        )
        # GetRawData - LocalLink
        ac, ir, hsib, sssd = self.ac, self._ir, self.hsib, self._sssd
        # SetRawMetrics
        # Semaphore, Event - LocalLink
        _wait_main, _sleep_logic, _acquire_wss = (
            self.wait_main,
            self.sleep_logic,
            self.acquire_wss,
        )
        # Methods - LocalLinks
        _get_raw_data, _decode_raw_data = (
            self._get_raw_data,
            self._decode_raw_data,
        )
        #  - - -
        try:
            engine = GridEngine.create(
                _mo_=self._mo, cfg=self.cfg, wait_reader=self.wait_reader
            )
            if isinstance(engine, GridEngine):
                while True:
                    try:
                        gc.collect()
                        _wait_main.wait()
                        if _raw_buf[sssd] != 1:
                            while _acquire_wss.acquire(block=False):
                                pass

                            _raw_buf[ir] = _raw_buf[ir + 1]
                            _raw_buf[sssd] = 1

                        while True:
                            if _get_status(_id_m_) is not True:
                                _set_status(_id_m_, 4)  # IDLE # TIME START
                                _acquire_wss.acquire()
                                if _get_status(_id_m_, proc=True):
                                    _sleep_logic.wait()
                                    break

                                _set_status(_id_m_, 5)  # Running # TIME WAKE_UP

                                if isinstance(
                                    (
                                        raw_data := _get_raw_data(
                                            ir=ir,
                                            ac=ac,
                                            hsib=hsib,
                                            _id_m_=_id_m_,
                                            _set_status=_set_status,
                                            _raw_buf=_raw_buf,
                                        )
                                    ),
                                    memoryview,
                                ):
                                    if isinstance(
                                        (
                                            trade := _decode_raw_data(
                                                _id_m_=_id_m_,
                                                decoder=_decoder,
                                                _set_status=_set_status,
                                                raw_data=raw_data,
                                            )
                                        ),
                                        AggTrade,
                                    ):
                                        if engine.update(
                                            price=trade.p,
                                            qty=trade.q,
                                            is_sell=trade.m,
                                            timestamp=trade.T,
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
                        _set_status(_id_m_, 150)  # Error in this func
                        break
            else:
                _set_status(_id_m_, 151)  # Error in engine
                return

        except Exception:
            traceback.print_exc()  # Debug
            _set_status(_id_m_, 150)  # Error in this func


def run_parsing(
    config: dict,
    sem_sleep_parsing: Semaphore,
    sleep_logic: Event,
    parser_monitor: Semaphore,
    general_event: Event,
    writer_sleep: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    agent = ParserAgent.create(
        cfg=config,
        sem_sleep_parsing=sem_sleep_parsing,
        sleep_logic=sleep_logic,
        parser_monitor=parser_monitor,
        general_event=general_event,
        writer_sleep=writer_sleep,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, ParserAgent):
        agent.run_parsing_engine()
