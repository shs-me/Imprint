import asyncio
import gc
import struct
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

import winloop
from websockets.asyncio.client import connect

from ... import Config, MonitorObj


class WSSAgent:
    def __init__(
        self, mo: MonitorObj, wake_up_parser: Event, general_event: Event
    ) -> None:
        __cfg = Config.CoreConfig
        self._mo = mo
        self._id_m_ = self._mo._id_m
        self._set, self._get = self._mo.set_, self._mo.get_
        self.release_parser = wake_up_parser
        self.wait_main = general_event
        # Variables
        self.uri = f"{Config.UserConfig.wss}{Config.UserConfig.wss}@aggTrade"
        # Semaphore, Event
        self.release_parser = wake_up_parser
        self.wait_main = general_event
        # RawSHM.buf
        self.raw_buf = self._mo.shms[__cfg.Raw.__name__]["buf"]
        # SetRawData
        self.cell_amount = __cfg.Raw.cell_amount
        self.data_size = __cfg.Raw.data_size
        self.header_size = __cfg.Raw.header_size
        self.flag, self.spare_flag = __cfg.Raw.flag, __cfg.Raw.spare_flag
        self.header_offset = __cfg.Raw.header_offset
        self.data_offset = __cfg.Raw.data_offset
        self.last_cell_offset = __cfg.Raw.last_cell_offset

    @staticmethod
    def create(
        wake_up_parser: Event,
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
                mo=mo, general_event=general_event, wake_up_parser=wake_up_parser
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
        dto: tuple[int, int],
        lco: tuple[int, int],
        id_m: int,
        set_status,
        raw_buf,
    ) -> bool:
        """
        Set RawData[JSON Bytes] to RawSHM.\n
        hro: Header Offset
        dto: Data Offset
        lco: Last Cell Offset
        """
        try:
            lrd: int = len(raw_data)  # lrd: Len Raw Data
            if lrd < data_size:
                flag_id: int = self.raw_buf[flag]
                _raw_buf = raw_buf[: dto[1]] if flag_id == 0 else raw_buf[dto[1] :]
                _raw_buf[self.spare_flag] = 1  # data maybe is dirty

                cell_id: int = struct.unpack("!q", _raw_buf[lco[0] : lco[1]])[0]

                if (cell_id + header_size) >= (cell_amount * header_size):
                    cell_id_new = header_size
                    cell_id = 0
                else:
                    cell_id_new = cell_id + header_size

                _raw_buf[lco[0] : lco[1]] = struct.pack("!q", cell_id_new)
                _raw_buf[cell_id_new] = lrd
                start = cell_id * data_size + dto[0]
                end = start + lrd
                _raw_buf[start:end] = raw_data

                _raw_buf[self.spare_flag] = 0  # data is not dirty
                return True

            else:
                set_status(id_m, 100)  # Warn in this IF
                return False

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m, 152)  # Error in this func
            return False

    async def run_wss_engine(self) -> None:
        # Local Links
        wake_up_parser = self.release_parser  # Semaphore
        _raw_buf = self.raw_buf  # RawShM.buf
        id_m, set_status, get_status = self._id_m_, self._set, self._get
        flag, header_size, data_size = self.flag, self.header_size, self.data_size
        cell_amount, dto, hro = self.cell_amount, self.data_offset, self.header_offset
        lco = self.last_cell_offset
        set_raw_data = self._set_raw_data
        # - - -
        while True:
            try:
                gc.collect()
                self.wait_main.wait()
                try:
                    async with connect(self.uri, ping_interval=20) as ws:
                        while True:
                            if get_status(id_m) is not True:
                                if get_status(id_m, proc=True):
                                    if wake_up_parser.is_set() is False:
                                        wake_up_parser.set()
                                    break

                                set_status(id_m, 4)  # Sleep
                                raw_data = await ws.recv(decode=False)
                                set_status(id_m, 5)  # WakeUp

                                if state := set_raw_data(
                                    raw_data=raw_data,
                                    flag=flag,
                                    cell_amount=cell_amount,
                                    header_size=header_size,
                                    data_size=data_size,
                                    dto=dto,
                                    lco=lco,
                                    id_m=id_m,
                                    set_status=set_status,
                                    raw_buf=_raw_buf,
                                ):
                                    if wake_up_parser.is_set() is False:
                                        wake_up_parser.set()

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
    wake_up_parser: Event,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    winloop.install()
    wss = WSSAgent.create(
        wake_up_parser=wake_up_parser,
        network_monitor=network_monitor,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(wss, WSSAgent):
        asyncio.run(wss.run_wss_engine())
