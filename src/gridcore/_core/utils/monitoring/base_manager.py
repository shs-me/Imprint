from abc import ABC

from ... import configurations as cfg


class Manager(ABC):
    cfgSetup: cfg.Setup
    cfgAccount: cfg.Account
    cfgStrategy: cfg.Strategy
    cfgCoin: cfg.Coin
    cfgFootprint: cfg.Footprint
    cfgMetrics: cfg.Metrics
    cfgDataStream: cfg.DataStream
    cfgUserStream: cfg.UserStream
    cfgSignal: cfg.Signal

    def __init__(
        self, segments: dict[str, slice], shm_buf: memoryview, configs: list
    ) -> None:
        self._segments: dict[str, slice] = segments
        self._shm_buf: memoryview = shm_buf
        self.configs_init(configs)

    def configs_init(self, configs: list) -> None:
        for attr_name, attr_type in self.__annotations__.items():
            for obj in configs:
                if isinstance(obj, attr_type):
                    setattr(self, attr_name, obj)
                    if issubclass(obj.__class__, cfg.SharedMemorySegments):
                        self.bind_shm_segments(obj)
                    break

    def bind_shm_segments(self, cfg: object) -> None:
        for attr_name in list(cfg.__dict__.keys()):
            attr_val = getattr(cfg, attr_name)
            if isinstance(attr_val, tuple):
                if len(attr_val) == 2:
                    shm: memoryview = self._shm_buf[
                        self._segments[cfg.__class__.__name__]
                    ]
                    setattr(cfg, attr_name, shm[slice(*attr_val)])
