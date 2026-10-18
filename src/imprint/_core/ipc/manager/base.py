"""Provide abstract shared memory segment binding and IPC attribute mapping."""

from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event, Lock, Semaphore
from types import GenericAlias
from typing import final

import imprint._core.configs as cfg
import imprint._core.ipc.memory_layouts as ml
from imprint._core.settings import StatusCodes
from imprint._core.utils.exc_dumper import DumpException


@dataclass(slots=True)
class Base(ABC):
    """Abstract base manager implementing core shared memory and IPC mechanisms.

    Binds configurations, memory layouts, and synchronization tools to class
    attributes for typed and flexible data access. Any new objects requiring
    binding must be specified in the class annotations.
    """

    _configs: list[list[cfg.Configuration]]
    _memory_layouts: list[ml.MemoryLayout]
    _segments: dict[str, slice]
    _shm_buf: memoryview
    _main_tools: list[Event | Semaphore]

    cfgSetup: cfg.Setup = field(init=False)
    cfgAccount: cfg.Account = field(init=False)
    cfgConnector: cfg.Connector = field(init=False)
    cfgRiskManagement: cfg.RiskManagement = field(init=False)
    cfgCoin: cfg.Coin = field(init=False)
    cfgFootprint: cfg.Footprint = field(init=False)

    mlMetrics: ml.Metrics = field(init=False)
    mlMarketDataStream: ml.MarketDataStream = field(init=False)
    mlMarketDataGapStream: ml.MarketDataGapStream = field(init=False)
    mlUserDataStream: ml.UserDataStream = field(init=False)
    mlOrderStream: ml.OrderStream = field(init=False)
    mlSignalStream: ml.SignalStream = field(init=False)
    mlLogStream: ml.LogStream = field(init=False)

    _sc_sem: Semaphore = field(init=False)
    _general_event: Event = field(init=False)
    _status_lock: Lock = field(init=False)

    _count_configs: int = field(default=0, init=False)
    _config_idx: int = field(default=0, init=False)
    _dumper: DumpException = field(
        default_factory=lambda: DumpException(), init=False
    )
    __procs_status: memoryview = field(init=False)

    @final
    def __post_init__(self) -> None:
        self._count_configs = len(self._configs)
        self.__bind_objs_with_attributes(self._main_tools)
        self.__bind_objs_with_attributes(self.__get_configs())
        self.__bind_objs_with_attributes(self._memory_layouts)
        self.__bind_shm_with_memory_layouts()
        self.__procs_status = self.mlMetrics.procs_status.view.cast("q")
        self._post_init()

    def _post_init(self) -> None: ...

    @final
    def __bind_objs_with_attributes(self, objs: Sequence[object]) -> None:
        """Bind list objects to attributes whose type matches their instance class.

        Generic attributes are skipped.
        """
        for obj in objs:
            for attr_name, attr_type in Base.__annotations__.items():
                if issubclass(attr_type.__class__, GenericAlias):
                    continue

                if isinstance(obj, attr_type):
                    setattr(self, attr_name, obj)
                    break

    @final
    def __bind_shm_with_memory_layouts(self) -> None:
        """Bind MemoryLayout instances to shared memory segments.

        Each layout receives a buffer of the requested size from shared memory,
        then partitions that buffer into its own sub-segments.
        """
        for layout in self._memory_layouts:
            buf: memoryview = self._shm_buf[
                self._segments[layout.__class__.__name__]
            ]
            layout.bind_memory(buf)
            layout.post_init_rings()

    @final
    def __get_configs(self) -> list[cfg.Configuration]:
        """Return the next configuration sequence in order."""
        configs = self._configs[self._config_idx]
        self._config_idx += 1
        return configs

    @final
    def __enter__(self) -> None: ...

    @final
    def __exit__(self, *args: object) -> None:
        self._dumper.dump_exception()
        self._child_exit_action()

    def _child_exit_action(self) -> None: ...

    @final
    def _change_configs(self) -> None:
        """Replace attributes annotated with Configuration subclasses with the next config set."""
        configs = self.__get_configs()
        self.__bind_objs_with_attributes(configs)

    @final
    def _reset(self) -> None:
        """Call reset on every attribute that is a MemoryLayout instance.

        Used to restore shared memory segments to their default state.
        """
        for attr_name, attr_type in Base.__annotations__.items():
            if issubclass(attr_type.__class__, GenericAlias):
                continue

            if issubclass(attr_type, ml.MemoryLayout):
                getattr(self, attr_name).reset()

    @final
    def _get_sc(self, pid: int) -> int:
        with self._status_lock:
            return self.__procs_status[pid]

    @final
    def _set_sc(self, pid: int, code: StatusCodes | int) -> None:
        with self._status_lock:
            self.__procs_status[pid] |= code

    @final
    def _clear_sc(self, pid: int, code: StatusCodes | int) -> None:
        with self._status_lock:
            self.__procs_status[pid] &= ~(code)
