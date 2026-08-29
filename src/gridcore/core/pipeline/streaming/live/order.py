import asyncio
import importlib
from multiprocessing.synchronize import Semaphore
from typing import override

from websockets import ClientConnection

from ....ipc import NodeManager
from ...utils.base_adapters import OrderEncoder
from .base import Base


class Order(Base):
    def __init__(self, manager: NodeManager, wss_sem: Semaphore) -> None:
        self.wss_sem: Semaphore = wss_sem

        m_name: str = manager.cfgSetup.order_encoder_module
        c_name: str = manager.cfgSetup.order_encoder_class_name
        encoder_type: type[OrderEncoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.order_encoder: OrderEncoder = encoder_type()
        self.send_order_uri: str = manager.cfgConnector.set_user_data_uri_for_wss

        super().__init__(manager, self.send_order_uri)

        self.loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        await self.loop.run_in_executor(None, self.wss_sem.acquire)

        if self.sus_wid[0] != self.sus_rid[0]:
            if raw_data := self.get_raw_data(
                reader_id=self.sus_rid,
                data=self.sus_data,
                data_header=self.sus_data_header,
                data_size=self.sus_data_size,
                cell_amount=self.sus_cell_amount,
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
