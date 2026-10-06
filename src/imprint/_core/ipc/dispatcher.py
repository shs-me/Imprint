"""Shared memory allocator and process client manager.

Coordinates the central IPC Dispatcher that dynamically analyzes configurations,
allocates shared memory blocks, handles memory layout segments, and instantiates
process-specific manager interfaces (Host or Node).
"""

import gc
import inspect
from copy import deepcopy
from dataclasses import dataclass, field
from multiprocessing import Event, Semaphore
from multiprocessing.shared_memory import SharedMemory
from types import FunctionType
from typing import Any

from imprint._core import configs
from imprint._core.configs import Configuration, SharedMemorySegments
from imprint._core.ipc.manager import HostManager, NodeManager
from imprint._core.settings import KwgsKeys as kk


@dataclass(slots=True)
class Dispatcher:
    """Allocate IPC resources, manage SharedMemory blocks, and instantiate manager interfaces.

    Coordinates the setup and alignment of inter-process communication resources.
    For the main orchestrator process, calculates segment layouts and initiates
    the shared memory block. For worker processes, attaches to existing shared
    memory and provides specialized Node managers.

    Parameters
    ----------
    is_main : bool
        True if this process is the main orchestrator (Host), False if it is a worker (Node).
    kwg : dict[str, Any]
        Keyword arguments dictionary containing configuration objects, status parameters,
        process identities, and shared synchronization tools.

    Attributes
    ----------
    shm : SharedMemory
        The SharedMemory instance allocated or attached to by this process.
    shm_buf : memoryview
        Raw memory buffer view mapping the entire SharedMemory segment.
    """

    is_main: bool
    kwg: dict[str, Any]

    shm: SharedMemory = field(init=False)
    shm_buf: memoryview = field(init=False)

    def run_client(self, func: FunctionType) -> None:
        """Initialize shared memory resources and execute target function with an assigned manager.

        Parameters
        ----------
        func : FunctionType
            The main function of the worker process or orchestrator to run.
            Receives the instantiated manager (HostManager or NodeManager) as a keyword argument.
        """
        if self.is_main:
            self.configurations_init()

        self.shm_init()

        manager = self.manager_init()
        gc.collect()
        gc.disable()
        func(manager=manager, **self.kwg)
        gc.collect()
        gc.enable()

    def configurations_init(self) -> None:
        """Scan configuration classes, calculate shared memory offsets, and create IPC synchronization tools.

        Inspects the `configs` module for subclasses of `Configuration` and
        `SharedMemorySegments`. Computes cumulative size requirements to derive memory slice
        offsets, updates keyword arguments, and initializes inter-process synchronization
        objects (Event, Semaphore).
        """
        offset: int = 0
        self.kwg[kk.Configs.name], self.kwg[kk.SegmentConfigs.name] = [], []
        self.kwg[kk.Segments.name] = {}
        for name, obj in inspect.getmembers(configs, inspect.isclass):
            if (
                issubclass(obj, Configuration)
                and (obj is not Configuration)
                and (obj is not SharedMemorySegments)
            ):
                c_obj: Configuration = (
                    self.kwg.pop(name) if name in self.kwg else obj()
                )
                if isinstance(c_obj, SharedMemorySegments):
                    self.kwg[kk.SegmentConfigs.name].append(c_obj)
                    self.kwg[kk.Segments.name][name] = slice(
                        offset, (offset := (offset + c_obj.shm_size))
                    )
                else:
                    self.kwg[kk.Configs.name].append(c_obj)

        self.kwg[kk.Segments.name][kk.ShmSize.name] = offset
        self.kwg[kk.MainTools.name] = [Event(), Semaphore(0)]

    def shm_init(self) -> tuple[SharedMemory, memoryview] | None:
        """Allocate a new SharedMemory block for the main process or attach to an existing segment for workers.

        Returns
        -------
        tuple[SharedMemory, memoryview] | None
            A tuple of the SharedMemory block and its associated memoryview block, or None.
        """
        if self.is_main:
            self.shm = SharedMemory(
                size=self.kwg[kk.Segments.name].pop(kk.ShmSize.name),
                create=True,
            )
            if self.shm.buf is not None:
                self.shm_buf = self.shm.buf
                self.shm_buf[:] = b"\x00" * self.shm.size

            self.kwg[kk.ShmName.name] = self.shm.name

        else:
            self.shm = SharedMemory(name=self.kwg.pop(kk.ShmName.name))
            if self.shm.buf is not None:
                self.shm_buf = self.shm.buf

    def manager_init(self) -> HostManager | NodeManager:
        """Instantiate HostManager or NodeManager matching the current process identity.

        Returns
        -------
        HostManager | NodeManager
            The instantiated manager object tailored to either the host's or worker's
            operational requirements.
        """
        configs = deepcopy(self.kwg[kk.Configs.name])
        segment_configs = deepcopy(self.kwg[kk.SegmentConfigs.name])
        segments = deepcopy(self.kwg[kk.Segments.name])
        if self.is_main:
            manager = HostManager(
                _configs=configs,
                _segment_configs=segment_configs,
                _segments=segments,
                _shm_buf=self.shm_buf,
                _main_tools=self.kwg[kk.MainTools.name],
            )
        else:
            manager = NodeManager(
                _configs=configs,
                _segment_configs=segment_configs,
                _segments=segments,
                _shm_buf=self.shm_buf,
                _main_tools=self.kwg[kk.MainTools.name],
                _proc_id=self.kwg["proc_id"],
                _task_id=self.kwg["task_id"],
            )
        return manager
