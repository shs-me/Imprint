import asyncio
import gc
import traceback
from multiprocessing.synchronize import Event, Semaphore

import winloop
from websockets.asyncio.client import connect

from ... import Config, MonitorObj


class WSSAgent:
    def __init__(
        self, mo: MonitorObj, wake_up_parser: Event, general_event: Event
    ) -> None:
        __cfg, self._mo = Config.CoreConfig, mo
        self._set, self._get, self.id_m = self._mo.set_, self._mo.get_, self._mo.id_m
        self.uri = f"{Config.UserConfig.wss}{Config.UserConfig.wss}@aggTrade"
        self.wake_up_parser, self.wait_main = wake_up_parser, general_event
        # InitGetRawData
        self.data_size, self.header_size = __cfg.Raw.data_size, __cfg.Raw.header_size
        self.data_offset = __cfg.Raw.data_offset[0]
        self.header_offset = __cfg.Raw.header_offset[0]
        self.cell_amount, self.safe_lag = __cfg.Raw.cell_amount, __cfg.Raw.safe_lag
        # SHM.buf
        self.raw_buf = self._mo.shms[__cfg.Raw.__name__]["buf"]
        self.ncell_wr = self.raw_buf[
            __cfg.Raw.ncell_offset[0] : __cfg.Raw.ncell_offset[1]
        ].cast("q")

    def _set_raw_data(
        self,
        raw_data: bytes,
        raw_buf: memoryview,
        ncell_wr: memoryview,
        cell_amount: int,
        header_size: int,
        header_offset: int,
        data_size: int,
        data_offset: int,
        safe_lag: float,
    ) -> bool:
        """
        Set RawData[JSON Bytes] to RawSHM.\n
        ncell_wr: number cell writer & reader
        """
        try:
            if (lrd := len(raw_data)) < data_size:  # lrd: Len Raw Data
                ncell_w, ncell_r = ncell_wr[0], ncell_wr[1]
                if ((ncell_w - ncell_r + cell_amount) % cell_amount) > safe_lag:
                    self._set(self.id_m, 101)  # Warn in this IF
                    return False

                raw_buf[ncell_w + header_offset] = lrd
                start = ncell_w * data_size + data_offset
                raw_buf[start : start + lrd] = raw_data
                ncell_wr[0] = (
                    ncell_w if (ncell_w := ncell_w + header_size) < cell_amount else 0
                )
                return True

            else:
                self._set(self.id_m, 100)  # Warn in this IF
                return False

        except Exception:
            traceback.print_exc()  # Debug
            self._set(self.id_m, 151)  # Error in this func
            return False

    async def run_wss_engine(self) -> None:
        # Local Links
        wake_up_parser = self.wake_up_parser
        id_m, set_status, get_status = self.id_m, self._set, self._get
        header_size, data_size = self.header_size, self.data_size
        data_offset, header_offset = self.data_offset, self.header_offset
        raw_buf, ncell_wr, cell_amount = self.raw_buf, self.ncell_wr, self.cell_amount
        safe_lag = self.safe_lag
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

                                if set_raw_data(
                                    raw_data=raw_data,
                                    raw_buf=raw_buf,
                                    ncell_wr=ncell_wr,
                                    cell_amount=cell_amount,
                                    header_size=header_size,
                                    header_offset=header_offset,
                                    data_size=data_size,
                                    data_offset=data_offset,
                                    safe_lag=safe_lag,
                                ):
                                    if wake_up_parser.is_set() is False:
                                        wake_up_parser.set()

                            else:
                                return

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
    try:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.network.__name__,
                _monitor=network_monitor,
                warn_error_status=warn_error_status,
            )
        except Exception:
            return

        agent = WSSAgent(
            mo=mo, general_event=general_event, wake_up_parser=wake_up_parser
        )
        asyncio.run(agent.run_wss_engine())
        agent = None

    finally:
        gc.collect()
