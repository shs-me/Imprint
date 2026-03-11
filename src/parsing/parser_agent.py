import gc
import sys
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
        sem_sleep_parsing: Semaphore,
        sem_sleep_logic: Semaphore,
        general_event: Event,
    ):
        # initializarion
        self._sa = sa

        self._set_status_, self._get_status_ = (
            self._sa._set_status,
            self._sa._get_status,
        )
        self.cfg = cfg
        self.sem_sleep_parsing = sem_sleep_parsing
        self.sem_sleep_logic = sem_sleep_logic
        self.general_event = general_event

        # variables init
        self._engine_id = 2
        self._tick_size = 0.01
        self.state: bytes | None = None
        self._decoder = msgspec.json.Decoder(AggTrade)

        # RawSHM.buf
        self._raw_buf = self._sa.shms["raw"]["buf"]
        # SignSHM.buf
        self._sign_buf = self._sa.shms["sign"]["buf"]
        # InitGetRawData
        self.ac: int = self.cfg["raw"]["ac"]  # Amount Cells
        self.dsib: int = self.cfg["raw"]["dsib"]  # Data size in bytes
        self.hsib: int = self.cfg["raw"]["hsib"]  # Headers size in bytes
        self._ir: int = self._sa.shms["raw"]["shm"].size - 2  # Index, Read _current_id
        self._irn: int = 0  # Index, Read Now
        self._iro: int = 0  # Index, Read Old
        self._lrd: int = 0  # Len raw data

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        sem_sleep_logic: Semaphore,
        general_event: Event,
        warn_error_status: Event,
    ):
        try:
            # Init SHM, DebugArray, StatusSHM
            sa = StatusAgent(
                proc_name="parsing",
                config=cfg,
                warn_error_status=warn_error_status,
            )
            return ParserAgent(
                sa=sa,
                cfg=cfg,
                sem_sleep_logic=sem_sleep_logic,
                sem_sleep_parsing=sem_sleep_parsing,
                general_event=general_event,
            )

        except Exception:
            warn_error_status.set()
            return None

    def _get_raw_data(
        self,
    ):  # Get Bytes from RawSHM: RING BUFFER
        try:
            self._iro = self._raw_buf[self._ir]

            if self._iro >= (self.ac * self.hsib):
                self._irn = self._raw_buf[self._ir] = self.hsib
                self._iro = 0
            else:
                self._irn = self._raw_buf[self._ir] = self.hsib + self._iro

            self._lrd = int.from_bytes(
                self._raw_buf[self._iro : self._irn], byteorder="little"
            )
            raw_data = self._raw_buf[
                (self._irn * self.ac) : ((self._irn * self.ac) + self._lrd)
            ]
            return raw_data

        except Exception:
            self._set_status_(154)
            return False

    def _decoder_raw_data(
        self,
        raw_data: memoryview,
    ):
        try:
            trade = self._decoder.decode(raw_data)
            return trade

        except Exception:
            self._set_status_(153)
            return False

    def _set_raw_signal(
        self,
    ):
        try:
            if isinstance(self.state, bytes):
                self._sign_buf[:4] = len(self.state).to_bytes(4, byteorder="little")
                self._sign_buf[4 : 4 + len(self.state)] = self.state
            else:
                return False

        except Exception:
            self._set_status_(152)  # Error in this func
            return False

    def run_parsing_engine(
        self,
        _warn_error_status,
    ):
        while True:
            try:
                gc.collect()
                self.general_event.wait()

                self._set_status_(10)  # Started
                engine = FootprintEngine.create(
                    cfg=self.cfg,
                    id_m=self._engine_id,
                    tick_size=self._tick_size,
                    warn_error_status=_warn_error_status,
                )
                if isinstance(engine, FootprintEngine):
                    while True:
                        if self._get_status_() is not True:
                            self._set_status_(4)  # IDLE
                            self.sem_sleep_parsing.acquire()
                            if self._get_status_(proc=True):
                                self._set_status_(2)  # Stoping
                                self.sem_sleep_logic.release()
                                break

                            self._set_status_(1)  # Running

                            if (raw_data := self._get_raw_data()) is not False:
                                if (
                                    trade := self._decoder_raw_data(raw_data)
                                ) is not False:
                                    self.state = engine.update(
                                        price=float(trade.p),
                                        qty=float(trade.q),
                                        is_sell=trade.m,
                                        timestamp=trade.E,
                                    )
                                    if self._set_raw_signal() is not False:
                                        self.sem_sleep_logic.release()
                        else:
                            print(22)
                            sys.exit()
                else:
                    self._set_status_(151)  # Error in engine
                    break

            except Exception as e:
                print(e, 78)
                self._set_status_(150)  # Error in this func
                break


def run_parsing(
    config: dict,
    sem_sleep_parsing: Semaphore,
    sem_sleep_logic: Semaphore,
    general_event: Event,
    warn_error_status: Event,
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
