import asyncio
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.synchronize import Event

from core.engine.network.rest_engine import RestEngine
from core.engine.network.wss_engine import WSsEngine
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office


class NetworkAgent:
    def __init__(self, wss: WSsEngine, rest: RestEngine, manager: AgentManager) -> None:
        self.wss, self.rest = wss, rest
        self.executor = ThreadPoolExecutor()

    async def _init_session(self) -> None:
        return

    async def run_network_engine(self) -> None:
        await self._init_session()
        await self.wss.run_wss_engine()


@manager_office()
def run_network(
    parsing_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    wss = WSsEngine(
        kwargs["manager"], wake_up_parser=parsing_event, general_event=general_event
    )
    rest = RestEngine(manager=kwargs["manager"])
    agent = NetworkAgent(wss=wss, rest=rest, manager=kwargs["manager"])
    asyncio.run(agent.run_network_engine())
