import asyncio
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.synchronize import Event, Semaphore

import winloop

from ... import Config, MonitorObj
from .. import shm_manager
from . import RestEngine, WSsEngine


class NetworkAgent:
    def __init__(self, wss: WSsEngine, rest: RestEngine) -> None:
        self.wss, self.rest = wss, rest
        self.executor = ThreadPoolExecutor()

    async def _init_session(self) -> None:
        return

    async def run_network_engine(self) -> None:
        await self._init_session()
        await self.wss.run_wss_engine()


@shm_manager(create=False)
def run_network(
    parsing_event: Event,
    general_event: Event,
    sc_sem: Semaphore,
    **kwargs,
) -> None:
    winloop.install()
    mo: MonitorObj = MonitorObj(
        shm_buf=kwargs["shm_buf"],
        proc_name=Config.CoreConfig.Status.network.__name__,
        sc_sem=sc_sem,
    )
    wss = WSsEngine(mo=mo, wake_up_parser=parsing_event, general_event=general_event)
    rest = RestEngine()
    agent = NetworkAgent(wss=wss, rest=rest)
    asyncio.run(agent.run_network_engine())
