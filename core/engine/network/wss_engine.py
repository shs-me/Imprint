from multiprocessing.synchronize import Event

from websockets.asyncio.client import connect

from core.constant import WS_STREAMS_PROD_URL
from core.utils.handlers import error_handler
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.status_codes import StatusCodes as scs


class WSsEngine:
    def __init__(
        self, manager: AgentManager, wake_up_parser: Event, general_event: Event
    ) -> None:
        self.manager: AgentManager = manager
        self.wake_up_parser: Event = wake_up_parser
        self.wait_main: Event = general_event

        self.set_proc_st = manager.set_proc_sc
        self.check_task = manager.check_task
        self.proc_status: memoryview = manager.proc_status
        self.task_status: memoryview = manager.task_status

        self.symbol: str = manager.symbol
        self.wss_aggTrades_url = f"{WS_STREAMS_PROD_URL}{self.symbol.lower()}@aggTrade"
        # InitGetRawData
        self.cfgRaw = self.manager.cfgRaw
        self.data_size: int = self.cfgRaw.data_size
        self.header_size: int = self.cfgRaw.header_size
        self.data_offset: int = self.cfgRaw.data[0]
        self.dataHeader_offset: int = self.cfgRaw.dataHeader[0]
        self.cell_amount: int = self.cfgRaw.cell_amount
        self.safe_lag: int = self.cfgRaw.safe_lag
        self.WriterCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.WriterCellCounter)
        ].cast("q")
        self.ReaderCellCounter: memoryview[int] = self.manager.raw_buf[
            slice(*self.cfgRaw.ReaderCellCounter)
        ].cast("q")

    @error_handler(set_status_code=True)
    async def run_wss_engine(self) -> None:
        # Local Links
        wake_up_parser = self.wake_up_parser
        # - - -
        proc_status, task_status = self.proc_status, self.task_status
        # - - -
        raw_buf = self.manager.raw_buf
        WCellC = self.WriterCellCounter
        data_size = self.data_size
        data_offset, dataHeader_offset = self.data_offset, self.dataHeader_offset
        cell_amount = self.cell_amount
        # - - -
        set_raw_data = self._set_raw_data
        # - - -
        while True:
            async with connect(self.wss_aggTrades_url, ping_interval=20) as ws:
                while True:
                    if proc_status[0] != 0 or task_status[0] != 0:
                        if task := self.check_task(complete=True):
                            return

                        elif task is False:
                            pass

                    raw_data = await ws.recv(decode=False)
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
            self.set_proc_st(code=scs.BIG_RAW_DATA)
            return False
