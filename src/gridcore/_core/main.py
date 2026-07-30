"""Core process launcher and lifecycle manager."""

import inspect
import os
from multiprocessing import Event, Process
from multiprocessing.synchronize import Event as EventT
from types import FunctionType

from loguru import logger

from .constant import DIRS_LIST
from .engine.general.execution import run_execution, run_execution_sim
from .engine.mode.backtest.logic_sim_agent import run_logic_sim
from .engine.mode.backtest.parsing_sim_agent import run_parsing_sim
from .engine.mode.backtest.wss_sim_agent import run_wss_sim
from .engine.mode.real.logic_agent import run_logic
from .engine.mode.real.parsing_agent import run_parsing
from .engine.mode.real.wss_agent import run_wss
from .settings import CoreResources, ProcsData
from .utils.handlers import supervisor
from .utils.monitoring.main_manager import MainManager


class MainAgent(CoreResources):
    """Process coordinator responsible for instantiating IPC tools and launching daemon processes."""

    def __init__(self, manager: MainManager, **kwargs) -> None:
        """Initializes synchronization events and process registry containers."""

        self.manager: MainManager = manager

        self.base_kwargs: dict = kwargs

        self.backtesting: bool = self.manager.cfgSetup.backtesting
        self.execution: bool = self.manager.cfgSetup.execution

        self.execution_event: EventT = Event()
        self.parsing_event: EventT = Event()
        self.logic_event: EventT = Event()

        self.procs: dict[int, ProcsData] = {}

    def run_core_engine(self) -> None:
        """Creates required output directories, spawns worker processes, and starts the MainManager loop."""

        logger.info("-- Core -- | Started, init...")
        try:
            self.check_dirs()
            if self.run_procs():
                logger.info("-- Core -- | Init completed.")

                self.manager.run(procs=self.procs)

        except KeyboardInterrupt:
            pass
        finally:
            logger.info("-- Core -- | Close the Core.")

    def check_dirs(self) -> None:
        """Ensures required working directories (data, logs, dump) exist on local disk."""

        for _dir in DIRS_LIST:
            if not os.path.exists(_dir):
                os.mkdir(_dir)

    def run_procs(self) -> bool:
        """Spawns configured worker processes and applies initial execution flags."""

        procs_funcs: list[FunctionType] = self.get_procs_funcs()
        count_procs: int = len(procs_funcs)
        procs_ids: list[int] = [i for i in range(count_procs)]
        task_ids: list[int] = [i + 10 for i in procs_ids]

        self.manager.general_event(False, task_ids)

        for proc_func, proc_id, task_id in zip(procs_funcs, procs_ids, task_ids):
            if (
                kwargs := self.get_kwargs_for_func(proc_func, proc_id, task_id)
            ) is None:
                return False

            self.run_proc(proc_func, kwargs)

        self.manager.general_event(True, task_ids)
        return True

    def get_procs_funcs(self) -> list[FunctionType]:
        """Resolves pipeline target functions based on backtesting and execution flags.

        Returns:
            list[FunctionType]: Process target functions for WSS, Parsing, Logic, and Execution.
        """

        funcs: list[FunctionType] = []
        funcs.append((run_wss_sim if self.backtesting else run_wss))
        funcs.append(run_parsing_sim if self.backtesting else run_parsing)
        funcs.append(run_logic_sim if self.backtesting else run_logic)
        if self.execution:
            funcs.append(run_execution_sim if self.backtesting else run_execution)

        return funcs

    def get_kwargs_for_func(
        self, func: FunctionType, proc_id: int, task_id: int
    ) -> dict | None:
        """Resolves required arguments for target worker process signatures.

        Args:
            func (FunctionType): Target process function.
            proc_id (int): Assigned process identifier.
            task_id (int): Assigned task status identifier.

        Returns:
            dict | None: Resolved keyword arguments or None if required parameters are missing.
        """

        sig: inspect.Signature = inspect.signature(func)
        proc_name: str = func.__name__.removeprefix("run_").upper()
        kwargs = {}
        for param_name in sig.parameters:
            if hasattr(self, param_name):
                val = getattr(self, param_name)
                kwargs[param_name] = val
            elif param_name == "kwargs":
                kwargs["proc_id"], kwargs["task_id"] = proc_id, task_id
            else:
                return logger.error(f"Missing arg: [{param_name}] for [{proc_name}]")

        kwargs = self.base_kwargs | kwargs

        self.procs[proc_id] = {"proc_name": proc_name, "task_id": task_id}  # type: ignore
        return kwargs

    def run_proc(self, func: FunctionType, kwargs: dict) -> None:
        """Spawns a target process as a daemon subprocess.

        Args:
            func (FunctionType): Target process function.
            kwargs (dict): Arguments passed to target process.
        """

        name: str = self.procs[kwargs["proc_id"]]["proc_name"]
        proc: Process = Process(
            target=func,
            kwargs=kwargs,
            name=name,
            daemon=True,
        )
        proc.start()
        self.procs[kwargs["proc_id"]]["proc"] = proc
        logger.success(f"-- Core -- | Process [{name}: pid[{proc.pid}]], started.")


@supervisor(is_main=True)
def run_core(**kwargs) -> None:
    """Supervisor-wrapped entry point for spawning the core multiprocessing architecture."""

    state = MainAgent(kwargs.pop("manager"), **kwargs)
    state.run_core_engine()
