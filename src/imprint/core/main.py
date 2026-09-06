"""Core process launcher and lifecycle manager."""

import inspect
import os
from dataclasses import dataclass, field
from multiprocessing import Event, Process, Semaphore
from multiprocessing.synchronize import Event as EventT
from multiprocessing.synchronize import Semaphore as SemT
from types import FunctionType
from typing import Any

from imprint.core.constant import DIRS_LIST
from imprint.core.ipc import HostManager, supervisor
from imprint.core.pipeline import run_engine, run_executing, run_streaming
from imprint.core.settings import LogLevel, ProcsData, ProcsIds


@dataclass(slots=True)
class MainAgent:
    """Process coordinator responsible for instantiating IPC tools and launching daemon processes."""

    manager: HostManager
    base_kwargs: dict[str, Any]
    procs: dict[int, ProcsData] = field(default_factory=dict, init=False)

    is_backtesting: bool = field(init=False)
    with_execution: bool = field(init=False)
    wss_sem: SemT = field(init=False)
    engine_event: EventT = field(init=False)
    execution_event: EventT = field(init=False)

    def __post_init__(self) -> None:
        self.is_backtesting = self.manager.cfgSetup.backtesting
        self.with_execution = self.manager.cfgSetup.execution

        self.wss_sem = Semaphore(0)
        self.engine_event = Event()
        self.execution_event = Event()

    def run_core_engine(self) -> None:
        """Creates required output directories, spawns worker processes, and starts the MainManager loop."""

        self.manager.logger("Init started.", LogLevel.INFO)
        try:
            self.check_dirs()
            if self.run_procs():
                self.manager.logger("Init completed", LogLevel.INFO)

                self.manager.run(procs=self.procs)

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

        procs_data: list[tuple[FunctionType, int]] = self.get_procs_funcs()
        procs_funcs: list[FunctionType] = [f for f, _ in procs_data]
        procs_ids: list[int] = [i for _, i in procs_data]
        task_ids: list[int] = [i + 10 for i in procs_ids]

        self.manager.general_event(False, task_ids)

        for proc_func, proc_id, task_id in zip(
            procs_funcs, procs_ids, task_ids
        ):
            if (
                kwargs := self.get_kwargs_for_func(proc_func, proc_id, task_id)
            ) is None:
                return False

            self.run_proc(proc_func, kwargs)

        self.manager.general_event(True, task_ids)
        return True

    def get_procs_funcs(self) -> list[tuple[FunctionType, int]]:
        funcs: list[tuple[FunctionType, int]] = []
        funcs.append((run_streaming, ProcsIds.streaming))
        funcs.append((run_engine, ProcsIds.engine))
        if self.with_execution:
            funcs.append((run_executing, ProcsIds.executing))

        return funcs

    def get_kwargs_for_func(
        self, func: FunctionType, proc_id: int, task_id: int
    ) -> dict[str, Any] | None:
        sig: inspect.Signature = inspect.signature(func)
        proc_name: str = func.__name__.split("_")[1].capitalize()
        kwargs: dict[str, Any] = {}
        for param_name in sig.parameters:
            if hasattr(self, param_name):
                val = getattr(self, param_name)
                kwargs[param_name] = val

            elif param_name == "kwargs":
                kwargs["proc_id"], kwargs["task_id"] = proc_id, task_id

            else:
                return self.manager.logger(
                    f"Missing arg: [{param_name}] for [{proc_name}]",
                    LogLevel.ERROR,
                )

        kwargs = self.base_kwargs | kwargs

        self.procs[proc_id] = {  # pyright: ignore[reportArgumentType]
            "proc_name": proc_name,
            "task_id": task_id,
        }
        return kwargs

    def run_proc(self, func: FunctionType, kwargs: dict[str, Any]) -> None:
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
def run(**kwargs: Any) -> None:
    """Supervisor-wrapped entry point for spawning the core multiprocessing architecture."""

    manager: HostManager = kwargs.pop("manager")
    state = MainAgent(manager, kwargs)
    state.run_core_engine()
