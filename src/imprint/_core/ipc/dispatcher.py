"""Shared memory allocator, process client manager, and supervisor context manager."""

import gc
import inspect
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field
from functools import wraps
from multiprocessing import Event, Lock, Semaphore
from multiprocessing.shared_memory import SharedMemory
from typing import Any

import imprint._core.ipc.memory_layouts as ml
from imprint._core.ipc.manager import HostManager, NodeManager
from imprint._core.settings import KwgsKeys as kk


@dataclass(slots=True)
class dispatcher:
    """Unified context manager, decorator, and IPC resource allocator.

    Coordinates shared memory allocation, memory layout initialization, manager
    instantiation, garbage collection state, and cleanup for host and worker processes.
    """

    is_main: bool = False

    kwg: dict[str, Any] = field(init=False)
    shm: SharedMemory | None = field(default=None, init=False)
    shm_buf: memoryview = field(init=False)
    manager: HostManager | NodeManager = field(init=False)

    def collect_memory_layouts(self) -> None:
        """Scan MemoryLayout classes, calculate offsets, and create IPC synchronization tools."""
        offset: int = 0
        self.kwg[kk.MemoryLayouts], self.kwg[kk.Segments] = [], {}
        for name, obj in inspect.getmembers(ml, inspect.isclass):
            if issubclass(obj, ml.MemoryLayout) and (
                obj is not ml.MemoryLayout
            ):
                c_obj: ml.MemoryLayout = (
                    self.kwg.pop(name) if name in self.kwg else obj()
                )
                self.kwg[kk.MemoryLayouts].append(c_obj)
                self.kwg[kk.Segments][name] = slice(
                    offset, (offset := (offset + c_obj.size))
                )

        self.kwg[kk.Segments][kk.ShmSize] = offset
        self.kwg[kk.MainTools] = [Event(), Semaphore(0), Lock()]

    def shm_init(self) -> None:
        """Allocate a new SharedMemory block for main process or attach to existing block for workers."""
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

    def manager_init(self) -> None:
        """Instantiate HostManager or NodeManager matching current process identity."""
        configs = deepcopy(self.kwg[kk.Configs])
        memory_layouts = deepcopy(self.kwg[kk.MemoryLayouts])
        segments = deepcopy(self.kwg[kk.Segments])

        if self.is_main:
            self.manager = HostManager(
                _configs=configs,
                _memory_layouts=memory_layouts,
                _segments=segments,
                _shm_buf=self.shm_buf,
                _main_tools=self.kwg[kk.MainTools],
            )
        else:
            self.manager = NodeManager(
                _configs=configs,
                _memory_layouts=memory_layouts,
                _segments=segments,
                _shm_buf=self.shm_buf,
                _main_tools=self.kwg[kk.MainTools],
                _pid=self.kwg["proc_id"],
                _tid=self.kwg["task_id"],
            )

    def __enter__(self) -> None:
        """Initialize layouts, shared memory, adjust GC, and process manager."""
        if self.is_main:
            self.collect_memory_layouts()

        self.shm_init()
        self.manager_init()
        gc.disable()
        gc.collect()

    def __exit__(self, *args: object) -> None:
        """Release buffers, close/unlink shared memory, and restore GC."""
        del self.manager
        gc.enable()
        gc.collect()
        if self.shm:
            self.shm_buf.release()
            self.shm.close()
            if self.is_main:
                self.shm.unlink()

    def __call__[**P, R](self, func: Callable[P, R]) -> Callable[P, R | None]:
        @wraps(wrapped=func)
        def wrapper(*_args: P.args, **kwargs: P.kwargs) -> R | None:
            self.kwg = kwargs
            with self, self.manager:
                func(manager=self.manager, **self.kwg)  # pyright: ignore[reportCallIssue]

        return wrapper
