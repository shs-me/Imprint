import asyncio
from asyncio import Task
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event, Semaphore

from ....ipc.manager import NodeManager
from ....settings import StatusCodes as scs
from .market_data import MarketData
from .order import Order
from .user_data import UserData


@dataclass(slots=True)
class Controller:
    manager: NodeManager
    engine_event: Event
    execution_event: Event
    wss_sem: Semaphore

    market_data_stream: MarketData = field(init=False)
    user_data_stream: UserData = field(init=False)
    order_stream: Order = field(init=False)

    def __post_init__(self) -> None:
        uri = self.manager.cfgConnector.market_data_uri_for_wss
        self.market_data_stream = MarketData(self.manager, uri, self.engine_event)
        uri = self.manager.cfgConnector.get_user_data_uri_for_wss
        self.user_data_stream = UserData(self.manager, uri, self.execution_event)
        uri = self.manager.cfgConnector.set_user_data_uri_for_wss
        self.order_stream = Order(self.manager, uri, self.wss_sem)

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
