import asyncio
import gc
import sys
from multiprocessing.synchronize import Event, Semaphore

import winloop
from websockets.asyncio.client import connect

from src.utils import StatusAgent


class WSSAgent:
    def __init__(
        self,
        sa: StatusAgent,
        cfg: dict,
        sem_sleep_parsing: Semaphore,
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
        self.sem_sleep_parsing = sem_sleep_parsing

        # variables
        self.url = f"{self.cfg['urls']['wsagg']}{self.cfg['argg']['symbol']}@aggTrade"

        # RawSHM.buf
        self._raw_buf = self._sa.shms["raw"]["buf"]

        # InitSetRawData
        self.ac: int = self.cfg["argg"]["raw"]["ac"]  # Amount Cells
        self.dsib: int = self.cfg["argg"]["raw"]["dsib"]  # Data size in bytes
        self.hsib: int = self.cfg["argg"]["raw"]["hsib"]  # Headers size in bytes
        self._iw: int = self._sa.shms["raw"]["shm"].size - 1  # Index, Write counter
        self._iwn: int = 0  # Index write new
        self._iwo: int = 0  # Index write old
        self._lrd: int = 0  # Len raw data

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        general_event: Event,
        warn_error_status: Event,
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
            )

        except Exception:
            warn_error_status.set()
            return None

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
            self._set_status_(151)  # Error in this func
            return False

    async def run_wss_engine(
        self,
    ):
        while True:
            try:
                gc.collect()

                self.general_event.wait()

                self._set_status_(10)  # Started. Conecting
                try:
                    async with connect(self.url, ping_interval=20) as ws:
                        self._set_status_(11)  # Connected
                        while True:
                            if self._get_status_() is not True:
                                if self._get_status_(proc=True):
                                    self._set_status_(2)  # Stoping
                                    self.sem_sleep_parsing.release()
                                    break

                                self._set_status_(4)  # IDLE
                                raw_data = await ws.recv(decode=False)
                                self._set_status_(1)  # Running

                                if self._set_raw_data(raw_data) is not False:
                                    self.sem_sleep_parsing.release()

                            else:
                                sys.exit()

                except Exception:
                    break

            except Exception:
                self._set_status_(150)  # Error in this func
                break


def run_wss(
    config: dict,
    sem_sleep_parsing: Semaphore,
    general_event: Event,
    warn_error_status: Event,
):
    gc.disable()

    winloop.install()

    wss = WSSAgent.create(
        cfg=config,
        sem_sleep_parsing=sem_sleep_parsing,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(wss, WSSAgent):
        asyncio.run(wss.run_wss_engine())
