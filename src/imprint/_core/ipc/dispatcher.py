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
from imprint._core.configs import MemoryLayout
from imprint._core.ipc.manager import HostManager, NodeManager
from imprint._core.settings import KwgsKeys as kk
from imprint._core.utils import error_handler


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

    shm: SharedMemory | None = field(default=None, init=False)
    shm_buf: memoryview = field(init=False)

    @error_handler
    def run_client(self, func: FunctionType) -> None:
        """Execute target function with an assigned manager.

        Parameters
        ----------
        func : FunctionType
            The main function of the worker process or orchestrator to run.
            Receives the instantiated manager (HostManager or NodeManager) as a keyword argument.
        """
        manager = self.manager_init()
        gc.collect()
        gc.disable()
        func(manager=manager, **self.kwg)

    def shm_segments_init(self) -> None:
        """Scan configuration classes, calculate shared memory offsets, and create IPC synchronization tools.

        Inspects the `configs` module for subclasses of `Configuration` and
        `MemoryLayout`. Computes cumulative size requirements to derive memory slice
        offsets, updates keyword arguments, and initializes inter-process synchronization
        objects (Event, Semaphore).
        """
        offset: int = 0
        self.kwg[kk.SegmentConfigs], self.kwg[kk.Segments] = [], {}
        for name, obj in inspect.getmembers(configs, inspect.isclass):
            if issubclass(obj, MemoryLayout) and (obj is not MemoryLayout):
                c_obj: MemoryLayout = (
                    self.kwg.pop(name) if name in self.kwg else obj()
                )
                self.kwg[kk.SegmentConfigs].append(c_obj)
                self.kwg[kk.Segments][name] = slice(
                    offset, (offset := (offset + c_obj.size))
                )

        self.kwg[kk.Segments][kk.ShmSize] = offset
        self.kwg[kk.MainTools] = [Event(), Semaphore(0)]

    def shm_init(self) -> None:
        """Allocate a new SharedMemory block for the main process or attach to an existing segment for workers."""
        if self.is_main:
            self.shm = SharedMemory(
                size=self.kwg[kk.Segments].pop(kk.ShmSize),
                create=True,
            )
            if self.shm.buf is not None:
                self.shm_buf = self.shm.buf
                self.shm_buf[:] = b"\x00" * self.shm.size

            self.kwg[kk.ShmName] = self.shm.name

        else:
            self.shm = SharedMemory(name=self.kwg.pop(kk.ShmName))
            if self.shm.buf is not None:
                self.shm_buf = self.shm.buf

    def manager_init(self) -> HostManager | NodeManager:
        """Instantiate HostManager or NodeManager matching the current process identity.

        Returns
        -------
        HostManager | NodeManager
            Instantiated manager object tailored to host or worker requirements.
        """
        configs = deepcopy(self.kwg[kk.Configs])
        segment_configs = deepcopy(self.kwg[kk.SegmentConfigs])
        segments = deepcopy(self.kwg[kk.Segments])
        if self.is_main:
            manager = HostManager(
                _configs=configs,
                _segment_configs=segment_configs,
                _segments=segments,
                _shm_buf=self.shm_buf,
                _main_tools=self.kwg[kk.MainTools],
            )
        else:
            manager = NodeManager(
                _configs=configs,
                _segment_configs=segment_configs,
                _segments=segments,
                _shm_buf=self.shm_buf,
                _main_tools=self.kwg[kk.MainTools],
                _proc_id=self.kwg["proc_id"],
                _task_id=self.kwg["task_id"],
            )
        return manager
