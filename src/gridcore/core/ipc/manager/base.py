"""Abstract shared memory segment binding manager."""

from abc import ABC
from multiprocessing.synchronize import Event, Semaphore

from ... import configs as cfg
from ...configs import Segment


class Base(ABC):
    """Base manager binding shared memory slice references to configuration objects."""

    cfgSetup: cfg.Setup
    cfgAccount: cfg.Account
    cfgConnector: cfg.Connector
    cfgRiskManagment: cfg.RiskManagment
    cfgCoin: cfg.Coin
    cfgFootprint: cfg.Footprint
    cfgMetrics: cfg.Metrics
    cfgDataStream: cfg.DataStream
    cfgGetUserStream: cfg.GetUserStream
    cfgSetUserStream: cfg.SetUserStream
    cfgSignal: cfg.Signal
    _text_stream: cfg.TextStream
    _sc_sem: Semaphore
    _general_event: Event

    def __init__(
        self,
        segments: dict[str, slice],
        shm_buf: memoryview,
        configs: list[cfg.Configuration],
        main_tools: list[Event | Semaphore],
    ) -> None:
        self._segments: dict[str, slice] = segments
        self._shm_buf: memoryview = shm_buf

        self.configs_init(configs)
        self.main_tools_init(main_tools)

        self._procs_status: memoryview = self.cfgMetrics.procs_status.view.cast("q")
        self._main_status: memoryview = self.cfgMetrics.main_status.view.cast("q")

        self._ts_safe_lag: int = self._text_stream.safe_lag
        self._ts_cell_amount: int = self._text_stream.cell_amount
        self._ts_data: memoryview = self._text_stream.data.view
        self._ts_data_size: int = self._text_stream.data_size
        self._ts_data_header: memoryview = self._text_stream.data_header.view.cast("q")
        self._ts_rid: memoryview = self._text_stream.reader_id.view.cast("q")
        self._ts_wid: memoryview = self._text_stream.writer_id.view.cast("q")

    def configs_init(self, configs: list[cfg.Configuration]) -> None:
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

        buf: memoryview = self._shm_buf[self._segments[cfg.__class__.__name__]]
        for attr_name in list(cfg.__dict__.keys()):
            attr_val = getattr(cfg, attr_name)
            if isinstance(attr_val, Segment):
                attr_val[buf[slice(*attr_val.offset)]]

    def main_tools_init(self, tools: list[Event | Semaphore]) -> None:
        """Binds IPC events and semaphores to manager attributes."""

        for attr_name, attr_type in self.__annotations__.items():
            for obj in tools:
                if isinstance(obj, attr_type):
                    setattr(self, attr_name, obj)
                    break
