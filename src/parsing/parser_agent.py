import gc
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

import msgspec

from src.parsing.footprint_engine import FootprintEngine
from src.utils import StatusAgent


class AggTrade(msgspec.Struct):
    E: int  # Event time
    p: str  # Price
    q: str  # Quantity
    m: bool  # Is buyer maker? (True=Sell)


class ParserAgent:
    def __init__(
        self,
        sa: StatusAgent,
        cfg: dict,
        decoder: msgspec.json.Decoder,
        sem_sleep_parsing: Semaphore,
        sem_sleep_logic: Semaphore,
        general_event: Event,
    ):
        # initializarion
        self._sa = sa
        self._get, self._set, self._ids_ = (
            self._sa.get_,
            self._sa.set_,
            self._sa._status(daughter=False),
        )
        self._id_m_, self._dgid_m_ = self._ids_

        self.cfg = cfg
        self.acquire_wss = sem_sleep_parsing
        self.release_logic = sem_sleep_logic
        self.wait_main = general_event

        # variables init
        self.tick_size = 0.01
        self.decoder: msgspec.json.Decoder = decoder

        # RawSHM.buf
        self.raw_buf = self._sa.shms["raw"]["buf"]
        # SignSHM.buf
        self.sign_buf = self._sa.shms["sign"]["buf"]
        # InitGetRawData
        self.ac: int = self.cfg["raw"]["ac"]  # Amount Cells
        self.dsib: int = self.cfg["raw"]["dsib"]  # Data size in bytes
        self.hsib: int = self.cfg["raw"]["hsib"]  # Headers size in bytes
        self.ir: int = self._sa.shms["raw"]["shm"].size - 2  # Index, Read _current_id

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        sem_sleep_logic: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ):
        try:
            # Init SHM, DebugArray, StatusSHM
            sa = StatusAgent(
                proc_name="parsing",
                config=cfg,
                warn_error_status=warn_error_status,
            )

            decoder = msgspec.json.Decoder(AggTrade)

            return ParserAgent(
                sa=sa,
                cfg=cfg,
                decoder=decoder,
                sem_sleep_logic=sem_sleep_logic,
                sem_sleep_parsing=sem_sleep_parsing,
                general_event=general_event,
            )

        except Exception:
            warn_error_status.release()
            return None

    def _get_raw_data(
        self,
        ir: int,
        ac: int,
        hsib: int,
        _id_m_,
        _dgid_m,
        _set_status,
        raw_buf: memoryview,
    ):
        try:
            iro = raw_buf[ir]
            if iro >= (ac * hsib):
                irn = raw_buf[ir] = hsib
                iro = 0
            else:
                irn = raw_buf[ir] = hsib + iro

            lrd = int.from_bytes(raw_buf[iro:irn], byteorder="little")
            raw_data = raw_buf[(irn * ac) : ((irn * ac) + lrd)]
            return raw_data

        except Exception:
            _set_status(_id_m_, _dgid_m, 154)
            return False

    def _decode_raw_data(
        self,
        _id_m_,
        _dgid_m,
        decoder,
        _set_status,
        raw_data: memoryview,
    ):
        try:
            trade = decoder(raw_data)
            return trade

        except Exception:
            _set_status(_id_m_, _dgid_m, 153)
            return False

    def _set_raw_signal(
        self,
        _id_m_,
        _dgid_m,
        _set_status,
        sign_buf,
        state: None | bytes,
    ):
        try:
            if isinstance(state, bytes):
                sign_buf[:4] = len(state).to_bytes(4, byteorder="little")
                sign_buf[4 : 4 + len(state)] = state
            else:
                return False

        except Exception:
            _set_status(_id_m_, _dgid_m, 152)  # Error in this func
            return False

    def run_parsing_engine(
        self,
        _warn_error_status,
    ):
        # JSON Decoder, SHM.Buf - LocalLink
        _raw_buf, _sign_buf, _decoder = self.raw_buf, self.sign_buf, self.decoder.decode
        # StatusAgents - LocalLink
        _id_m_, _dgid_m, _set_status, _get_status = (
            self._id_m_,
            self._dgid_m_,
            self._set,
            self._get,
        )
        # GetRawData - LocalLink
        _ac, _dsib, _hsib, _ir = self.ac, self.dsib, self.hsib, self.ir
        # Semaphore, Event - LocalLink
        _wait_main, _release_logic, _acquire_wss = (
            self.wait_main,
            self.release_logic,
            self.acquire_wss,
        )
        # Methods - LocalLinks
        _get_raw_data, _decode_raw_data, _set_raw_signal = (
            self._get_raw_data,
            self._decode_raw_data,
            self._set_raw_signal,
        )
        #  - - -
        while True:
            try:
                gc.collect()
                _wait_main.wait()
                _set_status(_id_m_, _dgid_m, 10)  # Started
                _raw_buf[_ir] = _raw_buf[_ir + 1]
                engine = FootprintEngine.create(
                    _sa_=self._sa,
                    cfg=self.cfg,
                    tick_size=self.tick_size,
                )
                if isinstance(engine, FootprintEngine):
                    while True:
                        if _get_status(_id_m_) is not True:
                            _set_status(_id_m_, _dgid_m, 4)  # IDLE # TIME START
                            _acquire_wss.acquire()
                            if _get_status(_id_m_, proc=True):
                                _set_status(_id_m_, _dgid_m, 2)  # Stoping
                                _release_logic.release()
                                break

                            _set_status(_id_m_, _dgid_m, 5)  # Running # TIME WAKE_UP

                            if (
                                raw_data := _get_raw_data(
                                    _ir,
                                    _ac,
                                    _hsib,
                                    _id_m_,
                                    _dgid_m,
                                    _set_status,
                                    _raw_buf,
                                )
                            ) is not False:
                                if (
                                    trade := _decode_raw_data(
                                        _id_m_,
                                        _dgid_m,
                                        _decoder,
                                        _set_status,
                                        raw_data,
                                    )
                                ) is not False:
                                    state = engine.update(
                                        price=float(trade.p),
                                        qty=float(trade.q),
                                        is_sell=trade.m,
                                        timestamp=trade.E,
                                    )
                                    if (
                                        _set_raw_signal(
                                            _id_m_,
                                            _dgid_m,
                                            _set_status,
                                            _sign_buf,
                                            state,
                                        )
                                        is not False
                                    ):
                                        _release_logic.release()

                            _set_status(_id_m_, _dgid_m, 6)  # Running # TIME END

                        else:
                            sys.exit()
                else:
                    _set_status(_id_m_, _dgid_m, 151)  # Error in engine
                    break

            except Exception:
                traceback.print_exc()
                _set_status(_id_m_, _dgid_m, 150)  # Error in this func
                break


def run_parsing(
    config: dict,
    sem_sleep_parsing: Semaphore,
    sem_sleep_logic: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
):
    gc.disable()
    agent = ParserAgent.create(
        cfg=config,
        sem_sleep_logic=sem_sleep_logic,
        sem_sleep_parsing=sem_sleep_parsing,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, ParserAgent):
        agent.run_parsing_engine(warn_error_status)
