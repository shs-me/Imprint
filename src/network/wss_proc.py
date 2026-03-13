import asyncio
import gc
import sys
import traceback
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
        self._get, self._set, self._id_m_ = (
            self._sa.get_,
            self._sa.set_,
            self._sa._status(daughter=False),
        )

        self.cfg = cfg
        self.release_parser = sem_sleep_parsing
        self.wait_main = general_event

        # variables
        self.url = f"{self.cfg['urls']['wsagg']}{self.cfg['argg']['symbol']}@aggTrade"

        # RawSHM.buf
        self.raw_buf = self._sa.shms["raw"]["buf"]

        # InitSetRawData
        self.ac: int = self.cfg["argg"]["raw"]["ac"]  # Amount Cells
        self.dsib: int = self.cfg["argg"]["raw"]["dsib"]  # Data size in bytes
        self.hsib: int = self.cfg["argg"]["raw"]["hsib"]  # Headers size in bytes
        self.iw: int = self._sa.shms["raw"]["shm"].size - 1  # Index, Write counter

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        network_monitor: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ):
        try:
            # Init SHM, DebugArray, StatusSHM
            sa = StatusAgent(
                proc_name="network_sim",
                config=cfg["argg"],
                _monitor=network_monitor,
                warn_error_status=warn_error_status,
            )
            return WSSAgent(
                sa=sa,
                cfg=cfg,
                general_event=general_event,
                sem_sleep_parsing=sem_sleep_parsing,
            )

        except Exception:
            traceback.print_exc()
            warn_error_status.release()
            return None

    def _set_raw_data(
        self,
        iw: int,
        ac: int,
        dsib: int,
        hsib: int,
        _id_m_,
        _set_status,
        raw_buf: memoryview,
        raw_data: bytes,
    ):  # Set Bytes to RawSHM: RING BUFFER
        try:
            lrd = len(raw_data)
            if lrd >= dsib:
                _set_status(_id_m_, 100)  # Warn in this IF
                return False

            iwo = raw_buf[iw]

            if iwo >= (ac * hsib):
                iwn = raw_buf[iw] = hsib
                iwo = 0
            else:
                iwn = raw_buf[iw] = hsib + iwo

            raw_buf[iwo:iwn] = lrd.to_bytes(4, byteorder="little")
            raw_buf[(iwn * ac) : ((iwn * ac) + lrd)] = raw_data

        except Exception:
            traceback.print_exc()
            _set_status(_id_m_, 151)  # Error in this func
            return False

    async def run_wss_engine(
        self,
    ):
        # JSON Decoder, SHM.Buf - LocalLink
        _raw_buf = self.raw_buf
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = (
            self._id_m_,
            self._set,
            self._get,
        )
        # GetRawData - LocalLink
        _ac, _dsib, _hsib, _iw = self.ac, self.dsib, self.hsib, self.iw
        # Semaphore, Event - LocalLink
        _wait_main, _release_parser = self.wait_main, self.release_parser
        # Methods - LocalLinks
        _set_raw_data = self._set_raw_data
        # Other - LocalLink
        uri = self.url
        # - - -
        while True:
            try:
                gc.collect()

                _wait_main.wait()
                try:
                    async with connect(uri, ping_interval=20) as ws:
                        while True:
                            if _get_status(_id_m_) is not True:
                                if _get_status(_id_m_, proc=True):
                                    _set_status(_id_m_, 2)  # Stoping
                                    _release_parser.release()
                                    break

                                _set_status(_id_m_, 4)  # IDLE # TIME START
                                raw_data = await ws.recv(decode=False)
                                _set_status(_id_m_, 5)  # Running

                                if (
                                    _set_raw_data(
                                        _iw,
                                        _ac,
                                        _dsib,
                                        _hsib,
                                        _id_m_,
                                        _set_status,
                                        _raw_buf,
                                        raw_data,
                                    )
                                    is not False
                                ):
                                    _release_parser.release()

                                _set_status(_id_m_, 6)  # END # TIME END

                            else:
                                sys.exit()

                except Exception:
                    break

            except Exception:
                traceback.print_exc()
                _set_status(_id_m_, 150)  # Error in this func
                break


def run_wss(
    config: dict,
    sem_sleep_parsing: Semaphore,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
):
    gc.disable()

    winloop.install()

    wss = WSSAgent.create(
        cfg=config,
        sem_sleep_parsing=sem_sleep_parsing,
        network_monitor=network_monitor,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(wss, WSSAgent):
        asyncio.run(wss.run_wss_engine())
