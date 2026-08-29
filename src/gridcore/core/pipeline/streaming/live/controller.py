import asyncio
from asyncio import Task
from multiprocessing.synchronize import Event, Semaphore

from ....ipc.manager import NodeManager
from ....settings import StatusCodes as scs
from .market_data import MarketData
from .order import Order
from .user_data import UserData


class Controller:
    def __init__(
        self,
        manager: NodeManager,
        engine_event: Event,
        execution_event: Event,
        wss_sem: Semaphore,
    ) -> None:
        self.manager: NodeManager = manager

        self.market_data_stream: MarketData = MarketData(manager, engine_event)
        # self.user_data_stream: UserData = UserData(manager, execution_event)
        # self.order_stream: Order = Order(manager, wss_sem)

    async def run_supervisor(self, streams: list[Task[None]]) -> None:
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(scs.EXIT, wait_main_task=False)

                if task & scs.COMPLETE:
                    self.market_data_stream.final_actions()
                    return self.manager.set_proc_sc(scs.COMPLETE, wait_main_task=False)

            for stream in streams:
                if stream.done():
                    return

            await asyncio.sleep(0.1)

    async def run_streams(self) -> None:
        async with asyncio.TaskGroup() as tg:
            streams: list[Task[None]] = [
                tg.create_task(self.market_data_stream.run()),
                # tg.create_task(self.user_data_stream.run()),
                # tg.create_task(self.order_stream.run()),
            ]
            supervisor: Task[None] = tg.create_task(self.run_supervisor(streams))
            await supervisor
