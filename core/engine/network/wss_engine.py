import gc
from multiprocessing.synchronize import Event

from websockets.asyncio.client import connect

from ... import AgentManager, error_handler
from ... import StatusCodes as sc
from ...constant import WS_STREAMS_PROD_URL


class WSsEngine:
    def __init__(
        self, manager: AgentManager, wake_up_parser: Event, general_event: Event
    ) -> None:
        self.manager = manager
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.uri = f"{WS_STREAMS_PROD_URL}{'dashusdt'}@aggTrade"
        self.wake_up_parser, self.wait_main = wake_up_parser, general_event
        # InitGetRawData
        self.cfgRaw = self.manager.cfgRaw
        self.data_size = self.cfgRaw.data_size
        self.header_size = self.cfgRaw.header_size
        self.data_offset: int = self.cfgRaw.data[0]
        self.dataHeader_offset: int = self.cfgRaw.dataHeader[0]
        self.cell_amount = self.cfgRaw.cell_amount
        self.safe_lag = self.cfgRaw.safe_lag
        self.WriterCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.WriterCellCounter)
        ].cast("q")
        self.ReaderCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.ReaderCellCounter)
        ].cast("q")

    def _set_raw_data(
        self,
        raw_data: bytes,
        raw_buf: memoryview,
        WCellC: memoryview,
        cell_amount: int,
        data_size: int,
        data_offset: int,
        dataHeader_offset: int,
    ) -> bool:
        if (lrd := len(raw_data)) < data_size:  # lrd: Len Raw Data
            cell: int = WCellC[0]  # get cell
            raw_buf[cell + dataHeader_offset] = lrd  # set lrd on cell[header]
            start: int = cell * data_size + data_offset
            raw_buf[start : start + lrd] = raw_data  # set raw data on cell[data]
            new_cell = cell + 1  # cell for next update
            WCellC[0] = new_cell if new_cell < cell_amount else 0
            return True

        else:
            self.set_status(code=sc.WARN0)
            return False

    @error_handler(set_status_code=True)
    async def run_wss_engine(self) -> None:
        # Local Links
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        wake_up_parser = self.wake_up_parser
        set_status, have_problem = self.set_status, self.have_problem
        raw_buf = self.manager.raw_buf
        WCellC = self.WriterCellCounter
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount = self.cell_amount
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
                            WCellC=WCellC,
                            cell_amount=cell_amount,
                            data_size=data_size,
                            data_offset=data_offset,
                            dataHeader_offset=dataHeader_offset,
                        ):
                            if wake_up_parser.is_set() is False:
                                wake_up_parser.set()

                    else:
                        return
