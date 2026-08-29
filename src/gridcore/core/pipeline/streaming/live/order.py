import asyncio
import importlib
from multiprocessing.synchronize import Event, Semaphore

from websockets.asyncio.client import connect

from ....ipc import NodeManager
from ...utils.base_adapters import UserStreamDecoder
from ...utils.rest_agent import RestAgent
from .user_data import UserData


class Order(UserData):
    def __init__(
        self,
        manager: NodeManager,
        engine_event: Event,
        wss_sem: Semaphore,
        execution_event: Event,
    ) -> None:
        super().__init__(manager, engine_event, wss_sem)

        self.execution_event: Event = execution_event

        m_name: str = manager.cfgSetup.user_stream_decoder_module
        c_name: str = manager.cfgSetup.user_stream_decoder_class_name
        decoder_type: type[UserStreamDecoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.decoder: UserStreamDecoder = decoder_type()
        self.rest: RestAgent = RestAgent(
            symbol=self.manager.cfgCoin.symbol, connector=self.manager.cfgConnector
        )
        self.user_data_uri: str = manager.cfgConnector.get_user_data_uri_for_wss

    async def run_order_stream(self) -> None:
        # Local Links
        wid, rid = self.gus_wid, self.gus_rid
        data, data_size = self.gus_data, self.gus_data_size
        data_header = self.gus_data_header
        cell_amount, safe_lag = self.gus_cell_amount, self.gus_safe_lag
        # - - -
        while True:
            # - - -
            async with connect(self.user_data_uri, ping_interval=20) as ws:
                while True:
                    if self.manager.have_status():
                        task: int = self.manager.check_base_task()
                        if isinstance(task, bool):
                            if task:
                                return

                    raw_data: bytes = await ws.recv(decode=False)

                    while self.lag_not_is_safe(wid, rid, cell_amount, safe_lag):
                        await asyncio.sleep(0)

                    if self.set_raw_data(
                        raw_data=raw_data,
                        writer_id=wid,
                        data=data,
                        data_header=data_header,
                        data_size=data_size,
                        cell_amount=cell_amount,
                    ):
                        if self.execution_event.is_set() is False:
                            self.execution_event.set()

    async def _listen_key_keepalive_loop(self):
        while True:
            await asyncio.sleep(30 * 60)
