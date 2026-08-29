import asyncio
from multiprocessing.synchronize import Event, Semaphore

from ....ipc.manager import NodeManager
from .set_user_data import SetUserData


class Router(SetUserData):
    def __init__(
        self,
        manager: NodeManager,
        engine_event: Event,
        execution_event: Event,
        wss_sem: Semaphore,
    ) -> None:
        super().__init__(manager, engine_event, execution_event, wss_sem)

    async def run_streams(self) -> None:
        asyncio.gather(
            self.run_market_data_stream(),
            self.run_get_user_data_stream(),
            self.run_set_user_data_stream(),
        )
