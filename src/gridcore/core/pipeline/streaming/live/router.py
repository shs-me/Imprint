import asyncio
from asyncio import Task
from multiprocessing.synchronize import Event, Semaphore

from ....ipc.manager import NodeManager
from ....settings import StatusCodes as scs
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

    async def run_supervisor(self) -> None:
        while True:
            if self.manager.have_status():
                task: int = self.manager.check_base_task()
                if task & scs.EXIT:
                    return self.manager.set_proc_sc(scs.EXIT, wait_main_task=False)

                if task & scs.COMPLETE:
                    self.final_actions()
                    return self.manager.set_proc_sc(scs.COMPLETE, wait_main_task=False)

            await asyncio.sleep(0)

    async def run_streams(self) -> None:
        async with asyncio.TaskGroup() as tg:
            supervisor: Task[None] = tg.create_task(self.run_supervisor())
            _md: Task[None] = tg.create_task(self.run_market_data_stream())
            _get_user: Task[None] = tg.create_task(self.run_get_user_data_stream())
            _set_user: Task[None] = tg.create_task(self.run_set_user_data_stream())

            await supervisor
