import asyncio
import gc
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

import winloop
from websockets.asyncio.client import connect

from ... import Config, MonitorObj


class WSSAgent:
    def __init__(
        self,
        mo: MonitorObj,
        sem_sleep_parsing: Semaphore,
        general_event: Event,
    ) -> None:
        # Initialization
        self._mo = mo
        self._id_m_ = self._mo._id_m
        self._set, self._get = self._mo.set_, self._mo.get_
        self.release_parser = sem_sleep_parsing
        self.wait_main = general_event
        # Variables
        self.uri = f"{Config.UserConfig.wss}{Config.UserConfig.wss}@aggTrade"
        # Semaphore, Event
        self.release_parser = sem_sleep_parsing
        self.wait_main = general_event
        # RawSHM.buf
        self.raw_buf = self._mo.shms[Config.CoreConfig.Raw.__name__]["buf"]
        # InitGetRawData
        self.cell_amount = Config.CoreConfig.Raw.cell_amount
        self.data_size = Config.CoreConfig.Raw.data_size
        self.header_size = Config.CoreConfig.Raw.header_size
        self.flag = Config.CoreConfig.Raw.flag
        self.flag_start = self.flag - 2

    @staticmethod
    def create(
        sem_sleep_parsing: Semaphore,
        network_monitor: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.network.__name__,
                _monitor=network_monitor,
                warn_error_status=warn_error_status,
            )
            return WSSAgent(
                mo=mo, general_event=general_event, sem_sleep_parsing=sem_sleep_parsing
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    def _set_raw_data(
        self,
        raw_data: bytes,
        flag: int,
        cell_amount: int,
        header_size: int,
        data_size: int,
        id_m: int,
        set_status,
        raw_buf: memoryview,
    ) -> bool:
        """Set RawData[JSON Bytes] to RawSHM"""
        try:
            lrd = len(raw_data)  # lrd: Len Raw Data
            if lrd < data_size:
                iwo = raw_buf[flag]  # iwo: Index Write Old
                if (iwo + 1) >= (cell_amount * header_size):
                    iwn = raw_buf[flag] = header_size  # iwn: Index Write New
                    iwo = 0
                else:
                    iwn = raw_buf[flag] = iwo + header_size

                raw_buf[iwo] = lrd  # Set lrd To Next Cell Hsib
                # Set RawData To Next Cell Dsib
                raw_buf[(iwn * cell_amount) : ((iwn * cell_amount) + lrd)] = raw_data
                return True

            else:
                set_status(id_m, 100)  # Warn in this IF
                return False

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m, 151)  # Error in this func
            return False

    async def run_wss_engine(self) -> None:
        # Local Links
        _release_parser = self.release_parser  # Semaphore
        _raw_buf = self.raw_buf  # RawShM.buf
        id_m, set_status, get_status = self._id_m_, self._set, self._get
        _cell_amount, _header_size = self.cell_amount, self.header_size
        _data_size, _flag, _flag_start = self.data_size, self.flag, self.flag_start
        set_raw_data = self._set_raw_data
        # - - -
        while True:
            try:
                gc.collect()
                self.wait_main.wait()
                while _raw_buf[_flag_start] != 1:
                    await asyncio.sleep(0.1)
                try:
                    async with connect(self.uri, ping_interval=20) as ws:
                        while True:
                            if get_status(id_m) is not True:
                                if get_status(id_m, proc=True):
                                    _release_parser.release()
                                    break

                                set_status(id_m, 4)  # Sleep
                                raw_data = await ws.recv(decode=False)
                                set_status(id_m, 5)  # WakeUp

                                if state := set_raw_data(
                                    raw_data=raw_data,
                                    flag=_flag,
                                    cell_amount=_cell_amount,
                                    header_size=_header_size,
                                    data_size=_data_size,
                                    id_m=id_m,
                                    set_status=set_status,
                                    raw_buf=_raw_buf,
                                ):
                                    _release_parser.release()

                                else:
                                    if state is False:
                                        pass
                            else:
                                sys.exit()

                except Exception:
                    traceback.print_exc()  # Debug
                    set_status(id_m, 150)  # Error in this func
                    break

            except Exception:
                traceback.print_exc()  # Debug
                set_status(id_m, 150)  # Error in this func
                break


def run_wss(
    sem_sleep_parsing: Semaphore,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    winloop.install()
    wss = WSSAgent.create(
        sem_sleep_parsing=sem_sleep_parsing,
        network_monitor=network_monitor,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(wss, WSSAgent):
        asyncio.run(wss.run_wss_engine())
