import gc
import struct
import sys
from multiprocessing.synchronize import Event, Semaphore

from src.utils import StatusAgent

# from src.logic.footprint_reading import FootprintReading


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
        self.general_event = general_event
        self.sem_sleep_logic = sem_sleep_logic

        # SignalSHM.buf
        self._sign_buf = self._sa.shms["sign"]["buf"]
        # GridSHM.buf
        self._grid_buf = self._sa.shms["grid"]["buf"]

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
    ):  # Get Bytes from SignSHM
        try:
            raw_sign = self._sign_buf[
                4 : 4 + int.from_bytes(self._sign_buf[:4], byteorder="little")
            ]

            idy, idx = struct.unpack("<II", raw_sign)

            return idy, idx

        except Exception:
            self._set(self._id_m_, 152)
            return False

    def run_logic_engine(
        self,
    ):
        while True:
            try:
                # self.reading = None
                gc.collect()

                self.general_event.wait()

                self._set(self._id_m_, 10)  # Started

                # if isinstance(reading, FootprintReading):
                while True:
                    if self._get(self._id_m_) is not True:
                        self._set(self._id_m_, 4)  # IDLE

                        self.sem_sleep_logic.acquire()
                        if self._get(self._id_m_, proc=True):
                            self._set(self._id_m_, 2)  # Stoping
                            break

                        self._set(self._id_m_, 1)  # Running
                        self._set(self._id_m_)  # TIME START

                        while self.sem_sleep_logic.acquire(block=False):
                            pass

                        if (ids := self._get_raw_signal()) is not False:
                            # reading.check_patterns(idy, idx)
                            idy, idx = ids
                            pass

                        self._set(self._id_m_)  # TIME END

                    else:
                        sys.exit()
                # self._set(self._id_m_, 151)  # Error in reading
                #
            except Exception:
                self._set(self._id_m_, 150)  # Error in this func
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
