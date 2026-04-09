from multiprocessing.synchronize import Event

from .. import AgentManager, manager_office
from . import WSsSimEngine


class NetworkSimAgent:
    def __init__(self, wss: WSsSimEngine, manager: AgentManager) -> None:
        self.manager, self.wss = manager, wss
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem

        self.cfgBT = self.manager.cfgBacktesting
        self.cfgMetrics = self.manager.cfgMetrics
        self.tick_size = self.cfgBT.tick_size
        self.lot_size = self.cfgBT.lot_size
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""

    def _init_session(self) -> None:
        tick_size, lot_size = self.tick_size, self.lot_size
        self.trade_par[2] = self.pricePrec = (
            len(tick_size.split(sep=".")[-1]) if "." in tick_size else 0
        )
        self.trade_par[3] = self.qtyPrec = (
            len(lot_size.split(sep=".")[-1]) if "." in lot_size else 0
        )
        self.pricMult, self.qtyMult = 10**self.pricePrec, 10**self.qtyPrec
        self.trade_par[0] = round(float(tick_size) * self.pricePrec)
        self.trade_par[1] = round(float(tick_size) * self.qtyPrec)

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
        kwargs["manager"], general_event=general_event, wake_up_parser=parsing_event
    )
    agent = NetworkSimAgent(wss=wss, manager=kwargs["manager"])
    agent.run_network_engine()
