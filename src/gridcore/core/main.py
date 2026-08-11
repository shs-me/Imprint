"""Core process launcher and lifecycle manager."""

import inspect
import os
from multiprocessing import Event, Process, Semaphore
from multiprocessing.synchronize import Event as EventT
from multiprocessing.synchronize import Semaphore as SemT
from types import FunctionType

from .constant import DIRS_LIST
from .ipc import HostManager, supervisor
from .pipeline import run_analyzing, run_executing, run_parsing, run_streaming
from .settings import (
    DataStreamProc,
    ExecutionProc,
    LogicProc,
    LogLevel,
    ParsingProc,
    ProcsData,
)


class MainAgent:
    """Process coordinator responsible for instantiating IPC tools and launching daemon processes."""

    market_data_wss: DataStreamProc
    parsing: ParsingProc
    logic: LogicProc
    execution: ExecutionProc

    def __init__(self, manager: HostManager, **kwargs) -> None:
        """Initializes synchronization events and process registry containers."""

        self.manager: HostManager = manager

        self.base_kwargs: dict = kwargs

        self.is_backtesting: bool = self.manager.cfgSetup.backtesting
        self.with_execution: bool = self.manager.cfgSetup.execution

        self.procs: dict[int, ProcsData] = {}

        self.execution_event: EventT = Event()
        self.parsing_event: EventT = Event()
        self.logic_event: EventT = Event()
        self.wss_sem: SemT = Semaphore(0)

        self.execution = ExecutionProc(10)

    def run_core_engine(self) -> None:
        """Creates required output directories, spawns worker processes, and starts the MainManager loop."""

        self.manager.logger("Init started.", LogLevel.INFO)
        try:
            self.check_dirs()
            if self.run_procs():
                self.manager.logger("Init completed", LogLevel.INFO)

                self.manager.run(
                    procs=self.procs,
                    market_data_wss=self.market_data_wss,
                    parsing=self.parsing,
                    logic=self.logic,
                    execution=self.execution,
                )

        except KeyboardInterrupt:
            pass
        finally:
            self.manager.logger("Close the core.\n", LogLevel.INFO)

    def check_dirs(self) -> None:
        """Ensures required working directories (data, logs, dump) exist on local disk."""

        for dir in DIRS_LIST:
            os.makedirs(dir, exist_ok=True)

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
        funcs.append(run_streaming)
        funcs.append(run_parsing)
        funcs.append(run_analyzing)
        if self.with_execution:
            funcs.append(run_executing)

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
        proc_name: str = func.__name__.split("_")[1].capitalize()
        kwargs = {}
        for param_name, param in sig.parameters.items():
            if hasattr(self, param_name):
                val = getattr(self, param_name)
                kwargs[param_name] = val
            elif param_name == "kwargs":
                kwargs["proc_id"], kwargs["task_id"] = proc_id, task_id
            elif param.annotation in self.__annotations__.values():
                for ann_name, ann in self.__annotations__.items():
                    if ann is param.annotation:
                        setattr(self, ann_name, proc_id)
            else:
                return self.manager.logger(
                    f"Missing arg: [{param_name}] for [{proc_name}]", LogLevel.ERROR
                )

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
        self.manager.logger(
            f"Process {name}: pid[{proc.pid}], started.", LogLevel.SUCCESS
        )


@supervisor(is_main=True)
def run_core(**kwargs) -> None:
    """Supervisor-wrapped entry point for spawning the core multiprocessing architecture."""

    state = MainAgent(kwargs.pop("manager"), **kwargs)
    state.run_core_engine()
