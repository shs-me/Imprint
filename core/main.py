import inspect
import os
from multiprocessing import Event, Process, Semaphore
from types import FunctionType

from loguru import logger

from . import Config, CoreResources, WatchDog, error_action, manager_office
from .engine import run_logic, run_network, run_network_sim, run_parsing


class RunMain(CoreResources):
    def __init__(self, backtesting: bool, shm_buf: memoryview) -> None:
        self.backtesting, self.cfg = backtesting, Config.ShmSharing
        self.shm_buf = shm_buf

        self.procs = {}
        self.sc_general = {}
        # Path's
        self.profiling_bin = Config.CorePath.profiling_bin
        # CoreResources
        self.parsing_event, self.logic_event = Event(), Event()
        self.sc_sem, self.general_event = Semaphore(0), Event()

    def _init_session(self) -> None:
        for _dir in Config.CorePath.dirs:
            if not os.path.exists(_dir):
                os.mkdir(_dir)

        self.funcs = [
            run_network_sim if self.backtesting else run_network,
            run_parsing,
            run_logic,
        ]

    def _get_kwargs_for_func(self, func: FunctionType) -> dict | None:
        sig = inspect.signature(func)
        proc_id = len(self.procs)
        proc_name = func.__name__.removeprefix("run_").upper()
        kwargs = {}
        for param_name in sig.parameters:
            if hasattr(self, param_name):
                val = getattr(self, param_name)
                kwargs[param_name] = val
            elif param_name == "kwargs":
                kwargs["proc_id"], kwargs["task_id"] = proc_id, proc_id + 10
                kwargs["sc_sem"] = self.sc_sem
            else:
                logger.error(f"Missing arg: [{param_name}] for [{proc_name}]")
                return None

        self.procs[proc_id] = {"proc_name": proc_name, "task_id": proc_id + 10}
        return kwargs

    def _run_proc(self, func) -> bool:
        kwargs = self._get_kwargs_for_func(func)
        if isinstance(kwargs, dict):
            name: str = self.procs[kwargs["proc_id"]]["proc_name"]
            p = Process(
                target=func,
                kwargs=kwargs,
                name=name,
                daemon=True,
            )
            p.start()
            self.procs[kwargs["proc_id"]]["proc"] = p
            logger.success(f"-- Core -- | Process [{name}], started.")
            return True

        else:
            logger.warning("-- Core -- | RunProc | kwargs is not dict")
            return False

    @error_action()
    def run_core_engine(self) -> None:
        logger.info("-- Core -- | Started, init...")
        self._init_session()
        for func in self.funcs:
            if self._run_proc(func=func) is False:
                return

        watchdog = WatchDog(
            procs=self.procs,
            shm_buf=self.shm_buf,
            general_event=self.general_event,
            sc_sem=self.sc_sem,
        )
        self.general_event.set()
        logger.info("-- Core -- | Init completed.")
        while True:
            if watchdog.run_watchdog_engine() is False:
                return


@manager_office(head_of_office=True)
def run_core(backtesting: bool, **kwargs) -> None:
    logger.remove()
    logger.add(
        Config.CorePath.core_log,
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    state = RunMain(backtesting=backtesting, shm_buf=kwargs["manager"])
    state.run_core_engine()
    logger.info("-- Core -- | Close the Core.")
