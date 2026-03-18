import asyncio
import gc
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

import winloop
from websockets.asyncio.client import connect

from .. import MonitorObj


class WSSAgent:
    def __init__(
        self,
        mo: MonitorObj,
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        general_event: Event,
    ) -> None:
        # Initialization
        self._mo = mo
        self._get, self._set, self._id_m_ = (
            self._mo.get_,
            self._mo.set_,
            self._mo._status(daughter=False),
        )

        self.cfg = cfg
        self.release_parser = sem_sleep_parsing
        self.wait_main = general_event

        # variables
        self.url = f"{self.cfg['urls']['wsagg']}{self.cfg['argg']['symbol']}@aggTrade"

        # RawSHM.buf
        self.raw_buf = self._mo.shms["raw"]["buf"]

        # InitSetRawData
        self.ac = self.cfg["argg"]["raw"]["ac"]  # Amount Cells
        self.dsib = self.cfg["argg"]["raw"]["dsib"]  # Data size in bytes
        self.hsib = self.cfg["argg"]["raw"]["hsib"]  # Headers size in bytes
        self._iw = self._mo.shms["raw"]["shm"].size - 1  # Index, Write counter
        self._sssd = self._mo.shms["raw"]["shm"].size - 3  # Index, Start Start Set Data

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_parsing: Semaphore,
        network_monitor: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            # Init SHM, profilingArray, StatusSHM
            mo = MonitorObj(
                proc_name="network_sim",
                config=cfg["argg"],
                _monitor=network_monitor,
                warn_error_status=warn_error_status,
            )
            return WSSAgent(
                mo=mo,
                cfg=cfg,
                general_event=general_event,
                sem_sleep_parsing=sem_sleep_parsing,
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    # Set Bytes to RawSHM
    def _set_raw_data(
        self,
        ac: int,
        iw: int,
        hsib: int,
        dsib: int,
        _id_m_,
        _set_status,
        raw_buf: memoryview,
        raw_data: bytes,
    ) -> bool:
        try:
            lrd = len(raw_data)  # lrd: Len Raw Data
            if lrd < dsib:  # dsib: Data Size in Bytes
                iwo = raw_buf[iw]  # iwo: Index Write Old
                if (iwo % (ac * hsib)) == 0:  # ac: Amount Cells
                    # hsib: Headers Size In Bytes
                    iwn = raw_buf[iw] = hsib  # iwn: Index Write New
                    iwo = 0
                else:
                    iwn = raw_buf[iw] = hsib + iwo

                # Set lrd To Next Cell Hsib
                raw_buf[iwo] = lrd
                # Set RawData To Next Cell Dsib
                raw_buf[(iwn * ac) : ((iwn * ac) + lrd)] = raw_data
                return True
            else:
                _set_status(_id_m_, 100)  # Warn in this IF
                return False

        except Exception:
            traceback.print_exc()  # Debug
            _set_status(_id_m_, 152)  # Error in this func
            return False

    async def run_wss_engine(
        self,
    ) -> None:
        # JSON Decoder, SHM.Buf - LocalLink
        _raw_buf = self.raw_buf
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = (
            self._id_m_,
            self._set,
            self._get,
        )
        # GetRawData - LocalLink
        ac, iw, hsib, dsib, sssd = self.ac, self._iw, self.hsib, self.dsib, self._sssd
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
                while _raw_buf[sssd] != 1:
                    await asyncio.sleep(0.1)
                try:
                    async with connect(uri, ping_interval=20) as ws:
                        while True:
                            if _get_status(_id_m_) is not True:
                                if _get_status(_id_m_, proc=True):
                                    _release_parser.release()
                                    break

                                _set_status(_id_m_, 4)  # Sleep
                                raw_data = await ws.recv(decode=False)
                                _set_status(_id_m_, 5)  # WakeUp

                                if (
                                    _state := _set_raw_data(
                                        ac=ac,
                                        iw=iw,
                                        hsib=hsib,
                                        dsib=dsib,
                                        _id_m_=_id_m_,
                                        _set_status=_set_status,
                                        raw_buf=_raw_buf,
                                        raw_data=raw_data,
                                    )
                                    is True
                                ):
                                    _release_parser.release()

                                else:
                                    if _state is False:
                                        pass
                            else:
                                sys.exit()

                except Exception:
                    break

            except Exception:
                traceback.print_exc()  # Debug
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
