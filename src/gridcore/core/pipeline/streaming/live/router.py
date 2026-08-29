import asyncio
from multiprocessing.synchronize import Event, Semaphore

from ....ipc.manager import NodeManager
from .order import Order


class Router(Order):
    def __init__(
        self,
        manager: NodeManager,
        engine_event: Event,
        wss_sem: Semaphore,
        execution_event: Event,
    ) -> None:
        super().__init__(manager, engine_event, wss_sem, execution_event)

    async def run_streams(self) -> None:
        asyncio.gather(
            self.run_market_data_stream(),
            self.run_user_data_stream(),
            self.run_order_stream(),
        )
