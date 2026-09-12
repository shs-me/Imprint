"""Shared memory allocator and process client manager.

This module provides the central IPC Dispatcher that dynamically analyzes configurations,
allocates shared memory, handles memory layout segments, and instantiates the correct
manager interface (Host or Node) based on the running process's role.
"""

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
    """IPC resource allocator instantiating SharedMemory blocks and manager interfaces.

    The Dispatcher coordinates the setup and alignment of IPC resources. For the main
    orchestrator process, it calculates segment layouts and initiates the SharedMemory block.
    For worker processes, it attaches to the existing SharedMemory block and returns
    specialized Node managers mapping their specific process IDs.

    Parameters
    ----------
    is_main : bool
        True if this process is the main orchestrator (Host), False if it is a worker (Node).
    kwg : dict[str, Any]
        Arguments dictionary containing configuration objects, status parameters,
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
        """Initialize shared memory resources and execute the target process function with an assigned Manager.

        Parameters
        ----------
        func : FunctionType
            The main function of the worker process or orchestrator to run.
            Receives the instantiated manager (HostManager or NodeManager) as a keyword argument.
        """
        if self.is_main:
            self.configurations_init()

        self.shm_init()

        func(manager=self.manager_init(), **self.kwg)

    def configurations_init(self) -> None:
        """Scan configuration module classes, calculate shared memory offsets, and create IPC sync tools.

        This method inspects the `configs` module for subclasses of `Configuration` and
        `SharedMemorySegments`. It calculates cumulative size requirements to derive memory slice
        offsets, updates keyword arguments, and initializes inter-process synchronization
        objects (Event, Semaphore).
        """
        offset: int = 0
        self.kwg[kk.Configs.name], self.kwg[kk.Segments.name] = [], {}
        for name, obj in inspect.getmembers(configs, inspect.isclass):
            if (
                issubclass(obj, Configuration)
                and (obj is not Configuration)
                and (obj is not SharedMemorySegments)
            ):
                c_obj: Configuration = (
                    self.kwg.pop(name) if name in self.kwg else obj()
                )
                self.kwg[kk.Configs.name].append(c_obj)
                if isinstance(c_obj, SharedMemorySegments):
                    self.kwg[kk.Segments.name][name] = slice(
                        offset,
                        (offset := (offset + c_obj.shm_size)),
                    )

        self.kwg[kk.Segments.name][kk.ShmSize.name] = offset
        self.kwg[kk.MainTools.name] = [Event(), Semaphore(0)]

    def shm_init(self) -> tuple[SharedMemory, memoryview] | None:
        """Allocate new SharedMemory block for main process or attach to existing segment for workers.

        Returns
        -------
        tuple[SharedMemory, memoryview] or None
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
        """Instantiate MainManager or NodeManager instance matching process identity.

        Returns
        -------
        HostManager or NodeManager
            The instantiated manager object tailored to either the host's or worker's
            operational requirements.
        """
        segments = deepcopy(self.kwg[kk.Segments.name])
        configs = deepcopy(self.kwg[kk.Configs.name])
        if self.is_main:
            manager = HostManager(
                _segments=segments,
                _shm_buf=self.shm_buf,
                _configs=configs,
                _main_tools=self.kwg[kk.MainTools.name],
            )
        else:
            manager = NodeManager(
                _proc_id=self.kwg["proc_id"],
                _task_id=self.kwg["task_id"],
                _segments=segments,
                _shm_buf=self.shm_buf,
                _configs=configs,
                _main_tools=self.kwg[kk.MainTools.name],
            )
        return manager
