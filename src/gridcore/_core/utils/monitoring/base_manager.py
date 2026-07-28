"""Abstract shared memory segment binding manager."""

from abc import ABC
from multiprocessing.synchronize import Event, Semaphore

from ... import configurations as cfg
from ...settings import ProcessFlags  # noqa: F401


class Manager(ABC):
    """Base manager binding shared memory slice references to configuration objects."""

    cfgSetup: cfg.Setup
    cfgAccount: cfg.Account
    cfgStrategy: cfg.Strategy
    cfgCoin: cfg.Coin
    cfgFootprint: cfg.Footprint
    cfgMetrics: cfg.Metrics
    cfgDataStream: cfg.DataStream
    cfgUserStream: cfg.UserStream
    cfgSignal: cfg.Signal
    _sc_sem: Semaphore
    _general_event: Event

    def __init__(
        self,
        segments: dict[str, slice],
        shm_buf: memoryview,
        configs: list,
        main_tools: list,
    ) -> None:
        self._segments: dict[str, slice] = segments
        self._shm_buf: memoryview = shm_buf
        self.configs_init(configs)
        self.main_tools_init(main_tools)

    def configs_init(self, configs: list) -> None:
        """Associates configuration class instances with manager attributes and shared memory segments."""

        for attr_name, attr_type in self.__annotations__.items():
            for obj in configs:
                if isinstance(obj, attr_type):
                    setattr(self, attr_name, obj)
                    if issubclass(obj.__class__, cfg.SharedMemorySegments):
                        self.bind_shm_segments(obj)
                    break

    def bind_shm_segments(self, cfg: object) -> None:
        """Binds tuple byte offsets to memoryview slices over active shared memory buffer."""

        for attr_name in list(cfg.__dict__.keys()):
            attr_val = getattr(cfg, attr_name)
            if isinstance(attr_val, tuple):
                if len(attr_val) == 2:
                    shm: memoryview = self._shm_buf[
                        self._segments[cfg.__class__.__name__]
                    ]
                    setattr(cfg, attr_name, shm[slice(*attr_val)])

    def main_tools_init(self, tools: list) -> None:
        """Binds IPC events and semaphores to manager attributes."""

        for attr_name, attr_type in self.__annotations__.items():
            for obj in tools:
                if isinstance(obj, attr_type):
                    setattr(self, attr_name, obj)
                    break
