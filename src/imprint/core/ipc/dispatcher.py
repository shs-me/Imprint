"""Shared memory allocator and process client manager."""

import inspect
from copy import deepcopy
from dataclasses import dataclass, field
from multiprocessing import Event, Semaphore
from multiprocessing.shared_memory import SharedMemory
from types import FunctionType
from typing import Any

from imprint.core import configs
from imprint.core.configs import Configuration, SharedMemorySegments
from imprint.core.ipc.manager import HostManager, NodeManager
from imprint.core.settings import KwgsKeys as kk


@dataclass(slots=True)
class Dispatcher:
    """IPC resource allocator instantiating SharedMemory blocks and manager interfaces."""

    is_main: bool
    kwg: dict[str, Any]

    shm: SharedMemory = field(init=False)
    shm_buf: memoryview = field(init=False)

    def run_client(self, func: FunctionType) -> None:
        """Initializes shared memory resources and executes target process function with assigned Manager."""

        if self.is_main:
            self.configurations_init()

        self.shm_init()

        func(manager=self.manager_init(), **self.kwg)

    def configurations_init(self) -> None:
        """Scans configuration module classes, calculates shared memory offsets, and creates IPC sync tools."""

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
        """Allocates new SharedMemory block for main process or attaches to existing segment for workers."""

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
        """Instantiates MainManager or NodeManager instance matching process identity."""

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
