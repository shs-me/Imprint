"""Core process launcher and lifecycle manager."""

import inspect
import os
from dataclasses import dataclass, field
from multiprocessing import Event, Process, Semaphore
from multiprocessing.synchronize import Event as EventT
from multiprocessing.synchronize import Semaphore as SemT
from types import FunctionType
from typing import Any

from imprint._core.constant import DIRS_LIST
from imprint._core.ipc import HostManager, supervisor
from imprint._core.pipeline import run_engine, run_executing, run_streaming
from imprint._core.settings import LogLevel, ProcsIds
from imprint._core.types import ProcsData


@dataclass(slots=True)
class MainAgent:
    """Process coordinator responsible for instantiating IPC tools and launching daemon processes.

    Parameters
    ----------
    manager : HostManager
        Active IPC host manager providing logging, state coordination, and configuration.
    base_kwargs : dict[str, Any]
        Base keyword arguments passed to all spawned child worker processes.

    Attributes
    ----------
    manager : HostManager
        Active IPC host manager.
    base_kwargs : dict[str, Any]
        Base keyword arguments shared across processes.
    procs : dict[int, ProcsData]
        Mapping of process identifiers to process metadata and instances.
    wss_sem : multiprocessing.synchronize.Semaphore
        Semaphore controlling WebSocket synchronization flow.
    engine_event : multiprocessing.synchronize.Event
        Event flag signaling engine state changes or synchronization boundaries.
    execution_event : multiprocessing.synchronize.Event
        Event flag signaling execution state transitions.
    """

    manager: HostManager
    base_kwargs: dict[str, Any]
    procs: dict[int, ProcsData] = field(default_factory=dict, init=False)

    wss_sem: SemT = field(default_factory=lambda: Semaphore(0), init=False)
    engine_event: EventT = field(default_factory=lambda: Event(), init=False)
    execution_event: EventT = field(default_factory=lambda: Event(), init=False)

    def run_core_engine(self) -> None:
        """Create required output directories, spawn worker processes, and start the MainManager loop.

        Initiates local filesystem structures, starts configured child processes,
        and hands control over to the IPC host manager main loop.
        """

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
        """Ensure required working directories (data, logs, dump) exist on local disk."""

        for dir in DIRS_LIST:
            os.makedirs(dir, exist_ok=True)

    def run_procs(self) -> bool:
        """Spawn configured worker processes and apply initial execution flags.

        Returns
        -------
        bool
            True if all worker processes successfully spawned and initialized; False otherwise.
        """

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
        """Retrieve the mapping of worker target functions and their corresponding process IDs.

        Returns
        -------
        list[tuple[FunctionType, int]]
            Collection of tuples containing the target callable and its process identifier.
        """
        funcs: list[tuple[FunctionType, int]] = []
        funcs.append((run_streaming, ProcsIds.streaming))
        funcs.append((run_engine, ProcsIds.engine))
        if self.manager.cfgSetup.execution:
            funcs.append((run_executing, ProcsIds.executing))

        return funcs

    def get_kwargs_for_func(
        self, func: FunctionType, proc_id: int, task_id: int
    ) -> dict[str, Any] | None:
        """Inspect target function signature and construct the keyword argument dictionary.

        Parameters
        ----------
        func : FunctionType
            Target worker function to inspect.
        proc_id : int
            Unique process identifier from ProcsIds.
        task_id : int
            Assigned task identifier associated with the process.

        Returns
        -------
        dict[str, Any] | None
            Constructed keyword argument mapping, or None if required arguments are missing.
        """
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
                self.manager.logger(
                    f"Missing arg: [{param_name}] for [{proc_name}]",
                    LogLevel.ERROR,
                )
                return None

        kwargs = self.base_kwargs | kwargs

        self.procs[proc_id] = {  # pyright: ignore[reportArgumentType]
            "proc_name": proc_name,
            "task_id": task_id,
        }
        return kwargs

    def run_proc(self, func: FunctionType, kwargs: dict[str, Any]) -> None:
        """Spawn a daemon multiprocessing Process for the given worker function and arguments.

        Parameters
        ----------
        func : FunctionType
            Target worker function executed as the process entry point.
        kwargs : dict[str, Any]
            Keyword arguments passed to the worker target function.
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
def run(**kwargs: Any) -> None:
    """Supervisor-wrapped entry point for spawning the core multiprocessing architecture.

    Parameters
    ----------
    **kwargs : Any
        Arbitrary keyword arguments including the required ``manager`` HostManager instance
        and core configuration settings.
    """

    manager: HostManager = kwargs.pop("manager")
    state = MainAgent(manager, kwargs)
    state.run_core_engine()
