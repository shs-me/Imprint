import inspect
from copy import deepcopy
from multiprocessing import Event, Semaphore
from multiprocessing.shared_memory import SharedMemory
from types import FunctionType

from ... import configurations
from ...configurations import Configuration, SharedMemorySegments
from ...settings import KwgsKeys as kk
from ..handlers import error_handler
from .agent_manager import AgentManager
from .main_manager import MainManager


class Dispatcher:
    def __init__(self, is_main: bool, **kwargs) -> None:
        self.is_main: bool = is_main
        self.kwg: dict = kwargs

    @error_handler()
    def run_client(self, func: FunctionType) -> None:
        if self.is_main:
            self.configurations_init()

        self.shm_init()

        func(manager=self.agent_init(), **self.kwg)

    def configurations_init(self) -> None:
        offset: int = 0
        self.kwg[kk.Configs.name], self.kwg[kk.Segments.name] = [], {}
        for name, obj in inspect.getmembers(configurations, inspect.isclass):
            if (
                issubclass(obj, Configuration)
                and (obj is not Configuration)
                and (obj is not SharedMemorySegments)
            ):
                c_obj: Configuration = self.kwg.pop(name) if name in self.kwg else obj()
                self.kwg[kk.Configs.name].append(c_obj)
                if isinstance(c_obj, SharedMemorySegments):
                    self.kwg[kk.Segments.name][name] = slice(
                        offset,
                        (offset := (offset + c_obj.shm_size)),
                    )

        self.kwg[kk.Segments.name][kk.ShmSize.name] = offset
        self.kwg[kk.MainTools.name] = [Event(), Semaphore(0)]

    def shm_init(self) -> tuple[SharedMemory, memoryview] | None:
        self.shm: SharedMemory
        self.shm_buf: memoryview

        if self.is_main:
            self.shm = SharedMemory(
                size=self.kwg[kk.Segments.name].pop(kk.ShmSize.name), create=True
            )
            if self.shm.buf is not None:
                self.shm_buf = self.shm.buf
                self.shm_buf[:] = b"\x00" * self.shm.size

            self.kwg[kk.ShmName.name] = self.shm.name

        else:
            self.shm = SharedMemory(name=self.kwg.pop(kk.ShmName.name))
            if self.shm.buf is not None:
                self.shm_buf = self.shm.buf

    def agent_init(self) -> MainManager | AgentManager:
        segments = deepcopy(self.kwg[kk.Segments.name])
        configs = deepcopy(self.kwg[kk.Configs.name])
        if self.is_main:
            manager = MainManager(
                segments=segments,
                shm_buf=self.shm_buf,
                configs=configs,
                main_tools=self.kwg[kk.MainTools.name],
            )
        else:
            manager = AgentManager(
                proc_id=self.kwg["proc_id"],
                task_id=self.kwg["task_id"],
                segments=segments,
                shm_buf=self.shm_buf,
                configs=configs,
                main_tools=self.kwg[kk.MainTools.name],
            )
        return manager
