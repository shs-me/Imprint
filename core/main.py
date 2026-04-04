import inspect
import os
import time
from multiprocessing import Event, Process, Semaphore
from multiprocessing.synchronize import Event as _Event
from multiprocessing.synchronize import Semaphore as _Semaphore
from typing import Protocol

from loguru import logger

from . import Config, IDpm, ProcsCfg, ProcsDictTyping, WatchDog
from . import error_action as err_action
from . import shm_manager as shm_m


class CoreResources(Protocol):
    parsing_event: _Event
    logic_event: _Event
    general_event: _Event
    sc_sem: _Semaphore


class RunMain(CoreResources):
    def __init__(self, backtesting: bool, shm_buf: memoryview) -> None:
        self.backtesting, self.core_cfg = backtesting, Config.CoreConfig
        self.shm_buf = shm_buf
        self.procs: dict[int, ProcsDictTyping] = {}
        self.id_info, self.sc_general = {}, {}
        # Path's
        self.profiling_bin = Config.CorePath.profiling_bin
        # CoreResources
        self.parsing_event, self.logic_event = Event(), Event()
        self.sc_sem, self.general_event = Semaphore(0), Event()

    def _init_session(self) -> None:
        for _dir in Config.CorePath.dirs:
            if not os.path.exists(_dir):
                os.mkdir(_dir)

        id_p = IDpm.network if self.backtesting else IDpm.network_sim
        self.procs, self.id_info = ProcsCfg.procs, Config.id_info
        self.procs.pop(id_p)
        self.id_info.pop(id_p)

    def _close_(self) -> None:
        logger.warning(
            "-- Core -- | _Exit | Closing Processes, DampProfilingArray, Clean SHM-s, Exit..."
        )
        for id, data in self.procs.items():
            if data["proc"] is not None and data["proc"].is_alive():
                data["proc"].terminate()
                data["proc"].join()
                logger.warning(
                    f"-- Core -- | _Exit | Process {self.procs[id]['name']} closed"
                )

    def _proc_arg_init(self, func) -> tuple | None:
        sig = inspect.signature(func)
        args_to_pass = []
        for param_name in sig.parameters:
            if hasattr(self, param_name):
                val = getattr(self, param_name)
                args_to_pass.append(val)
            else:
                if param_name == "kwargs":
                    pass
                else:
                    logger.error(f"Missing arg: {param_name} for {func.__name__}")
                    return None

        return tuple(args_to_pass)

    def _run_proc(self, id_proc: int) -> bool:
        """Create & Run Procces's"""
        _arg = self._proc_arg_init(self.procs[id_proc]["func"])
        if isinstance(_arg, tuple):
            p = Process(
                target=self.procs[id_proc]["func"],
                args=_arg,
                name=self.procs[id_proc]["name"],
                daemon=True,
            )
            p.start()
            self.procs[id_proc]["proc"] = p
            return True

        else:
            logger.warning("-- Core -- | RunProc | Arg for Proc is not tuple")
            return False

    @err_action()
    def run_core_engine(self) -> bool | None:
        logger.info("--- Core --- Started. Init...")
        self._init_session()
        _watchdog = WatchDog(
            procs=self.procs,
            id_info=self.id_info,
            shm_buf=self.shm_buf,
            general_event=self.general_event,
            sc_sem=self.sc_sem,
        )
        logger.info("WatchDog | Started")
        for id_proc in self.procs:  # Init Process's
            if self._run_proc(id_proc=id_proc) is False:
                logger.warning(
                    "--- Core --- | RunCoreEngine | Closing because of the WatchDog"
                )
                return False

            time.sleep(0.5)

        self.general_event.set()
        logger.info("--- Core --- Init Completed.")
        while True:
            if _watchdog.run_watchdog_engine() is False:
                return False


@shm_m(create=True)
def run_core(backtesting: bool, **kwargs) -> None:
    logger.remove()
    logger.add(
        Config.CorePath.core_log,
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    state = RunMain(backtesting=backtesting, shm_buf=kwargs["shm_buf"])
    if state.run_core_engine() is False:
        state._close_()
