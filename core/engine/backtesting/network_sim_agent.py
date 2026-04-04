from multiprocessing.synchronize import Event, Semaphore

from ... import Config, MonitorObj
from .. import shm_manager
from . import WSsSimEngine


class NetworkSimAgent:
    def __init__(self, wss: WSsSimEngine, mo: MonitorObj) -> None:
        __cfg, self._mo, self.wss = Config.CoreConfig, mo, wss
        self.id_m, self.have_watchdog_task = self._mo.id_m, self._mo.have_watchdog_task
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.tick_size = Config.UserConfig.tick_size
        self.tick_size_buf: memoryview[float] = self._mo.metrics_buf[
            slice(*__cfg.Metrics.tick_size)
        ].cast("d")
        self.price_buf: memoryview[float] = self._mo.metrics_buf[
            slice(*__cfg.Metrics.price)
        ].cast("d")

    def _init_session(self) -> None:
        self.tick_size_buf[0] = self.tick_size

    def run_network_engine(self) -> None:
        self._init_session()
        self.wss.run_wss_sim_engine()


@shm_manager(create=False)
def run_network_sim(
    parsing_event: Event,
    general_event: Event,
    sc_sem: Semaphore,
    **kwargs,
) -> None:
    mo: MonitorObj = MonitorObj(
        shm_buf=kwargs["shm_buf"],
        proc_name=Config.CoreConfig.Status.network_sim.__name__,
        sc_sem=sc_sem,
    )
    wss: WSsSimEngine = WSsSimEngine(
        mo=mo, general_event=general_event, wake_up_parser=parsing_event
    )
    agent = NetworkSimAgent(wss=wss, mo=mo)
    agent.run_network_engine()
