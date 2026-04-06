from multiprocessing.synchronize import Event

from ... import Config, ManagerAgent
from .. import manager_office
from . import WSsSimEngine


class NetworkSimAgent:
    def __init__(self, wss: WSsSimEngine, manager: ManagerAgent) -> None:
        __cfg, self.manager, self.wss = Config.ShmSharing, manager, wss
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = (
            self.manager.set_status,
            self.manager.have_problem,
        )
        self.tick_size = Config.UserConfig.tick_size
        self.lot_size = Config.UserConfig.lot_size
        self.pricePrec, self.qtyPrec = 0, 0
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            __cfg.Metrics.tick_size[0] : __cfg.Metrics.qtyPrecision[1]
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


@manager_office(head_of_office=False)
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
