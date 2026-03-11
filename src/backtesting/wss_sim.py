import gc
import sys
import time
from multiprocessing.synchronize import Event, Semaphore

import msgspec

from src.utils import StatusAgent


class WSSAgent:
    def __init__(
        self,
        sa: StatusAgent,
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        general_event: Event,
        file_path: str,
    ):
        # Initialization
        self._sa = sa
        self._set_status_, self._get_status_ = (
            self._sa._set_status,
            self._sa._get_status,
        )
        self.cfg: dict = cfg
        self.file_path: str = file_path
        self.general_event: Event = general_event
        self.sem_sleep_parsing: Semaphore = sem_sleep_parsing

        self.encoder = msgspec.json.Encoder()

        # RawSHM.buf
        self._raw_buf = self._sa.shms["raw"]["buf"]

        # InitGetRawData
        self.ac = self.cfg["argg"]["raw"]["ac"]  # Amount Cells
        self.dsib = self.cfg["argg"]["raw"]["dsib"]  # Data size in bytes
        self.hsib = self.cfg["argg"]["raw"]["hsib"]  # Headers size in bytes
        self._iw = self._sa.shms["raw"]["shm"].size - 1  # Index, Write counter
        self._iwn = 0  # Index Write Now
        self._iwo = 0  # Index Write Old
        self._lrd = 0  # Len raw data

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        general_event: Event,
        warn_error_status: Event,
        file_path: str,
    ):
        try:
            # Init SHM, DebugArray, StatusSHM
            sa = StatusAgent(
                proc_name="network_sim",
                config=cfg["argg"],
                warn_error_status=warn_error_status,
            )
            return WSSAgent(
                sa=sa,
                cfg=cfg,
                general_event=general_event,
                sem_sleep_parsing=sem_sleep_parsing,
                file_path=file_path,
            )

        except Exception:
            warn_error_status.set()
            return None

    def _line_to_raw_data(
        self,
        line: str,
    ):  # Line from file convert to raw_data for simulation:
        try:
            data = line.strip().split(",")
            raw_data = self.encoder.encode(
                {
                    "E": int(data[5]),  # transact_time
                    "p": data[1],  # price
                    "q": data[2],  # quantity
                    "m": bool(data[6]),  # is_buyer_maker
                }
            )
            return raw_data

        except Exception:
            self._set_status_(153)  # Error in this func
            return False

    def _set_raw_data(
        self,
        raw_data: bytes,
    ):  # Set Bytes to RawSHM: RING BUFFER
        try:
            self._lrd = len(raw_data)
            if self._lrd >= self.dsib:
                self._set_status_(100)  # Warn in this IF
                return False

            self._iwo = self._raw_buf[self._iw]

            if self._iwo >= (self.ac * self.hsib):
                self._iwn = self._raw_buf[self._iw] = self.hsib
                self._iwo = 0
            else:
                self._iwn = self._raw_buf[self._iw] = self.hsib + self._iwo

            self._raw_buf[self._iwo : self._iwn] = self._lrd.to_bytes(
                4, byteorder="little"
            )
            self._raw_buf[
                (self._iwn * self.ac) : ((self._iwn * self.ac) + self._lrd)
            ] = raw_data

        except Exception:
            self._set_status_(152)  # Error in this func
            return False

    def run_wss_sim_engine(
        self,
    ):
        while True:
            try:
                gc.collect()
                self.general_event.wait()

                self._set_status_(10)  # Starting
                try:
                    with open(self.file_path, "r") as self.f:
                        self._set_status_(11)  # Connected
                        next(self.f)
                        for line in self.f:
                            if self._get_status_() is not True:
                                if self._get_status_(proc=True):
                                    self._set_status_(2)  # Stoping
                                    self.sem_sleep_parsing.release()
                                    break

                                self._set_status_(1)  # Running
                                if (
                                    raw_data := self._line_to_raw_data(line)
                                ) is not False:
                                    if self._set_raw_data(raw_data) is not False:
                                        self.sem_sleep_parsing.release()

                                self._set_status_(4)  # IDLE
                                time.sleep(0.005)

                            else:
                                sys.exit()

                except FileNotFoundError:
                    self._set_status_(151)
                    break

            except Exception:
                self._set_status_(150)
                break


def run_wss_sim(
    config: dict,
    sem_sleep_parsing: Semaphore,
    general_event: Event,
    warn_error_status: Event,
):
    gc.disable()

    wss = WSSAgent.create(
        cfg=config,
        sem_sleep_parsing=sem_sleep_parsing,
        general_event=general_event,
        warn_error_status=warn_error_status,
        file_path="data/aggtrades.csv",
    )

    if isinstance(wss, WSSAgent):
        wss.run_wss_sim_engine()
