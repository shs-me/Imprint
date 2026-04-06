import gc
from multiprocessing.synchronize import Event

from websockets.asyncio.client import connect

from ... import Config, ManagerAgent
from ... import StatusCodes as sc
from .. import error_action


class WSsEngine:
    def __init__(
        self, manager: ManagerAgent, wake_up_parser: Event, general_event: Event
    ) -> None:
        __cfg, self.manager = Config.ShmSharing, manager
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.uri = f"{Config.UserConfig.wss}{Config.UserConfig.wss}@aggTrade"
        self.wake_up_parser, self.wait_main = wake_up_parser, general_event
        # InitGetRawData
        self.data_size, self.header_size = __cfg.Raw.data_size, __cfg.Raw.header_size
        self.data_offset = __cfg.Raw.data_offset[0]
        self.header_offset = __cfg.Raw.header_offset[0]
        self.cell_amount = __cfg.Raw.cell_amount
        # SHM.buf
        self.ncell_wr = self.manager.raw_buf[slice(*__cfg.Raw.ncell_offset)].cast("q")

    def _set_raw_data(
        self,
        raw_data: bytes,
        raw_buf: memoryview,
        ncell_wr: memoryview,
        cell_amount: int,
        header_offset: int,
        data_size: int,
        data_offset: int,
    ) -> bool:
        if (lrd := len(raw_data)) < data_size:  # lrd: Len Raw Data
            ncell_w: int = ncell_wr[0]  # get cell
            raw_buf[ncell_w + header_offset] = lrd  # set lrd on cell[header]
            start: int = ncell_w * data_size + data_offset
            raw_buf[start : start + lrd] = raw_data  # set raw data on cell[data]
            ncell_w_new = ncell_w + 1  # cell for next update
            ncell_wr[0] = ncell_w_new if ncell_w_new < cell_amount else 0
            return True

        else:
            self.set_status(code=sc.WARN0)  # Warn in this IF
            return False

    @error_action(set_sc=True)
    async def run_wss_engine(self) -> None:
        # Local Links
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        wake_up_parser = self.wake_up_parser
        set_status, have_problem = self.set_status, self.have_problem
        data_size = self.data_size
        data_offset, header_offset = self.data_offset, self.header_offset
        raw_buf, ncells, acell = self.manager.raw_buf, self.ncell_wr, self.cell_amount
        set_raw_data, have_task = self._set_raw_data, self.have_task
        # - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            async with connect(self.uri, ping_interval=20) as ws:
                while True:
                    set_status(code=SLEEP)
                    if have_problem() is False:
                        if have_task():
                            if wake_up_parser.is_set() is False:
                                wake_up_parser.set()
                                break

                        raw_data = await ws.recv(decode=False)
                        set_status(code=WAKE_UP)

                        if set_raw_data(
                            raw_data=raw_data,
                            raw_buf=raw_buf,
                            ncell_wr=ncells,
                            cell_amount=acell,
                            header_offset=header_offset,
                            data_size=data_size,
                            data_offset=data_offset,
                        ):
                            if wake_up_parser.is_set() is False:
                                wake_up_parser.set()

                    else:
                        return
