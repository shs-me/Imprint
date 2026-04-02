import gc
from multiprocessing.synchronize import Event, Semaphore

from ... import Config, MonitorObj
from .. import shm_load
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


def run_network_sim(
    wake_up_parser: Event,
    network_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    if (data := shm_load()) is None:
        return

    shm, shm_buf = data
    mo: MonitorObj = MonitorObj(
        shm_buf=shm_buf,
        proc_name=Config.CoreConfig.Status.network_sim.__name__,
        warn_error_status=warn_error_status,
        monitor=network_monitor,
    )

    wss: WSsSimEngine = WSsSimEngine(
        mo=mo, general_event=general_event, wake_up_parser=wake_up_parser
    )
    agent = NetworkSimAgent(wss=wss, mo=mo)
    try:
        agent.run_network_engine()
    except KeyboardInterrupt:
        pass

    del agent, wss, mo
    shm_buf.release()
    shm.close()
    gc.collect()
