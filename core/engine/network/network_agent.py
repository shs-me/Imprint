import asyncio
import gc
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.synchronize import Event, Semaphore

import winloop

from ... import Config, MonitorObj
from .. import shm_load
from . import RestEngine, WSsEngine


class NetworkAgent:
    def __init__(self, wss: WSsEngine, rest: RestEngine) -> None:
        self.wss, self.rest = wss, rest
        self.executor = ThreadPoolExecutor()

    async def _init_session(self) -> None:
        pass

    async def run_network_engine(self) -> None:
        await self._init_session()
        await self.wss.run_wss_engine()


def run_network(
    wake_up_parser: Event,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    winloop.install()
    if (data := shm_load()) is None:
        return

    shm, shm_buf = data
    mo: MonitorObj = MonitorObj(
        shm_buf=shm_buf,
        proc_name=Config.CoreConfig.Status.network.__name__,
        warn_error_status=warn_error_status,
        monitor=network_monitor,
    )
    wss = WSsEngine(mo=mo, general_event=general_event, wake_up_parser=wake_up_parser)
    rest = RestEngine()
    agent = NetworkAgent(wss=wss, rest=rest)
    try:
        asyncio.run(agent.run_network_engine())
    except KeyboardInterrupt:
        pass

    del agent, wss, rest, mo
    shm_buf.release()
    shm.close()
    gc.collect()
