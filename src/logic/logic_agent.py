import gc
import struct
import sys
from multiprocessing.synchronize import Event, Semaphore

from src.logic.footprint_reader import FootprintReader
from src.utils import StatusAgent


class LogicAgent:
    def __init__(
        self,
        sa: StatusAgent,
        cfg: dict,
        sem_sleep_logic: Semaphore,
        general_event: Event,
    ):
        # Initialization
        self._sa = sa
        self._get, self._set, self._id_m_ = (
            self._sa.get_,
            self._sa.set_,
            self._sa._status(daughter=False),
        )

        self.cfg = cfg
        self.acquire_parser = sem_sleep_logic
        self.wait_main = general_event

        # SignalSHM.buf
        self.sign_buf = self._sa.shms["sign"]["buf"]

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_logic: Semaphore,
        general_event: Event,
        warn_error_status: Event,
    ):
        try:
            # Init SHM, DebugArray, StatusSHM
            sa = StatusAgent(
                proc_name="logic",
                config=cfg,
                warn_error_status=warn_error_status,
            )
            return LogicAgent(
                sa=sa,
                cfg=cfg,
                sem_sleep_logic=sem_sleep_logic,
                general_event=general_event,
            )

        except Exception:
            warn_error_status.set()
            return None

    def _get_raw_signal(
        self,
        sign_buf,
        set_status,
        id_m: int,
    ):
        try:
            raw_sign = sign_buf[
                4 : 4 + int.from_bytes(sign_buf[:4], byteorder="little")
            ]

            idy, idx = struct.unpack("<II", raw_sign)

            return idy, idx

        except Exception:
            set_status(id_m, 152)
            return False

    def run_logic_engine(
        self,
    ):
        # JSON Decoder, SHM.Buf - LocalLink
        _sign_buf = self.sign_buf
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = self._id_m_, self._set, self._get
        # Semaphore, Event - LocalLink
        _wait_main, _acquire_parser = self.wait_main, self.acquire_parser
        # Methods - LocalLinks
        _get_raw_signal = self._get_raw_signal
        # - - -
        while True:
            try:
                gc.collect()

                _wait_main.wait()

                _set_status(_id_m_, 10)  # Started
                reader = FootprintReader()
                if isinstance(reader, FootprintReader):
                    while True:
                        if _get_status(_id_m_) is not True:
                            _set_status(_id_m_, 4)  # IDLE # TIME START

                            _acquire_parser.acquire()
                            if _get_status(_id_m_, proc=True):
                                _set_status(_id_m_, 2)  # Stoping
                                break

                            _set_status(_id_m_, 5)  # Running # TIME WACK_UP

                            while _acquire_parser.acquire(block=False):
                                pass

                            if (
                                ids := _get_raw_signal(_sign_buf, _set_status, _id_m_)
                            ) is not False:
                                reader.check_patterns(ids[0], ids[1])

                            _set_status(_id_m_, 6)  # END # TIME END

                        else:
                            sys.exit()
                else:
                    _set_status(_id_m_, 151)  # Error in reading
                    break

            except Exception:
                _set_status(_id_m_, 150)  # Error in this func
                break


def run_logic(
    config: dict,
    sem_sleep_logic: Semaphore,
    general_event: Event,
    warn_error_status: Event,
):

    gc.disable()
    agent = LogicAgent.create(
        cfg=config,
        sem_sleep_logic=sem_sleep_logic,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, LogicAgent):
        agent.run_logic_engine()
