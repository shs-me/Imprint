from multiprocessing.synchronize import Event

from core.engine.network_sim.rest_sim_engine import RestSimAgent
from core.engine.network_sim.wss_sim_engine import WSsSimEngine
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office


class NetworkSimAgent:
    def __init__(
        self, manager: AgentManager, wss: WSsSimEngine, rest: RestSimAgent
    ) -> None:
        self.manager: AgentManager = manager
        self.wss: WSsSimEngine = wss
        self.rest: RestSimAgent = rest

        self.set_proc_sc = manager.set_proc_sc
        self.check_task = manager.check_task
        self.task_status: memoryview = manager.task_status
        self.proc_status: memoryview = manager.proc_status

        self.cfgBT = self.manager.cfgBacktesting
        self.cfgMetrics = self.manager.cfgMetrics
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""

    def _init_session(self) -> None:
        self.ts = self.rest.get_tick_size()
        self.ls = self.rest.get_lot_size()
        self.trade_par[2] = self.pricePrec = (
            len(self.ts.split(sep=".")[-1]) if "." in self.ts else 0
        )
        self.trade_par[3] = self.qtyPrec = (
            len(self.ls.split(sep=".")[-1]) if "." in self.ls else 0
        )
        self.pricMult, self.qtyMult = 10**self.pricePrec, 10**self.qtyPrec
        self.trade_par[0] = round(float(self.ts) * self.pricePrec)
        self.trade_par[1] = round(float(self.ls) * self.qtyPrec)

    def run_network_engine(self) -> None:
        self._init_session()
        self.wss.run_wss_sim_engine()


@manager_office()
def run_network_sim(
    parsing_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    wss: WSsSimEngine = WSsSimEngine(
        manager=kwargs["manager"],
        general_event=general_event,
        wake_up_parser=parsing_event,
    )
    rest: RestSimAgent = RestSimAgent(manager=kwargs["manager"])
    agent = NetworkSimAgent(manager=kwargs["manager"], wss=wss, rest=rest)
    agent.run_network_engine()
