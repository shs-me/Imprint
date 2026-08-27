import importlib
from multiprocessing.synchronize import Event, Semaphore

from websockets.asyncio.client import connect

from ....ipc import NodeManager
from ...utils.base_adapters import OrderEncoder
from .market_data import MarketData


class UserData(MarketData):
    def __init__(
        self, manager: NodeManager, engine_event: Event, wss_sem: Semaphore
    ) -> None:
        super().__init__(manager, engine_event)

        self.wss_sem: Semaphore = wss_sem
        m_name: str = manager.cfgSetup.order_encoder_module
        c_name: str = manager.cfgSetup.order_encoder_class_name
        encoder_type: type[OrderEncoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.order_encoder: OrderEncoder = encoder_type()
        self.send_order_uri: str = manager.cfgConnector.set_user_data_uri_for_wss

    async def run_user_data_stream(self) -> None:
        # Local Links
        wss_sem = self.wss_sem
        wid, rid = self.sus_wid, self.sus_rid
        data, data_size = self.sus_data, self.sus_data_size
        data_header = self.sus_data_header
        cell_amount = self.sus_cell_amount
        get_raw_data = self.get_raw_data
        # - - -
        while True:
            # - - -
            async with connect(self.send_order_uri, ping_interval=20) as ws:
                while True:
                    if self.manager.have_status():
                        task: int = self.manager.check_base_task()
                        if isinstance(task, bool):
                            if task:
                                return

                    wss_sem.acquire()

                    if wid[0] != rid[0]:
                        if raw_data := get_raw_data(
                            reader_id=rid,
                            data=data,
                            data_header=data_header,
                            data_size=data_size,
                            cell_amount=cell_amount,
                        ):
                            await ws.send(raw_data, text=True)

    def get_raw_data(
        self,
        reader_id: memoryview,
        data: memoryview,
        data_header: memoryview,
        data_size: int,
        cell_amount: int,
    ) -> memoryview:
        cell: int = reader_id[0]
        lrd = data_header[cell]
        start: int = cell * data_size
        raw_data: memoryview = data[start : start + lrd]
        new_cell = cell + 1
        reader_id[0] = new_cell if new_cell < cell_amount else 0
        return raw_data
