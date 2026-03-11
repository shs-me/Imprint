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
        self._set_status_, self._get_status_ = (
            self._sa._set_status,
            self._sa._get_status,
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
            self._set_status_(152)
            return False

    def run_logic_engine(
        self,
    ):
        while True:
            try:
                # self.reading = None
                gc.collect()

                self.general_event.wait()

                self._set_status_(10)  # Started

                # if isinstance(reading, FootprintReading):
                while True:
                    if self._get_status_() is not True:
                        self._set_status_(4)  # IDLE

                        self.sem_sleep_logic.acquire()
                        if self._get_status_(proc=True):
                            self._set_status_(2)  # Stoping
                            break

                        self._set_status_(1)  # Running
                        while self.sem_sleep_logic.acquire(block=False):
                            pass

                        if (ids := self._get_raw_signal()) is not False:
                            # reading.check_patterns(idy, idx)
                            print(type(ids[0]))
                            pass

                    else:
                        sys.exit()
                # self._set_status_(151)  # Error in reading
                #
            except Exception:
                self._set_status_(150)  # Error in this func
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
