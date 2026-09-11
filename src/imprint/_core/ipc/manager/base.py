"""Abstract shared memory segment binding manager."""

from abc import ABC
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event, Semaphore
from types import GenericAlias
from typing import final

from imprint._core import configs as cfg
from imprint._core.configs import RingBuf, Segment


@dataclass(slots=True)
class Base(ABC):
    """Base manager binding shared memory slice references to configuration objects."""

    _segments: dict[str, slice]
    _shm_buf: memoryview
    _configs: list[cfg.Configuration]
    _main_tools: list[Event | Semaphore]

    cfgSetup: cfg.Setup = field(init=False)
    cfgAccount: cfg.Account = field(init=False)
    cfgConnector: cfg.Connector = field(init=False)
    cfgRiskManagement: cfg.RiskManagement = field(init=False)
    cfgCoin: cfg.Coin = field(init=False)
    cfgFootprint: cfg.Footprint = field(init=False)
    cfgMetrics: cfg.Metrics = field(init=False)
    cfgDataStream: cfg.DataStream = field(init=False)
    cfgGetUserStream: cfg.GetUserStream = field(init=False)
    cfgSetUserStream: cfg.SetUserStream = field(init=False)
    cfgSignal: cfg.Signal = field(init=False)

    _log_stream: cfg.LogStream = field(init=False)
    _sc_sem: Semaphore = field(init=False)
    _general_event: Event = field(init=False)

    _procs_status: memoryview = field(init=False)
    _main_status: memoryview = field(init=False)
    _ts_safe_lag: int = field(init=False)
    _ts_cell_amount: int = field(init=False)
    _ts_data: memoryview = field(init=False)
    _ts_data_size: int = field(init=False)
    _ts_data_header: memoryview = field(init=False)
    _ts_rid: memoryview = field(init=False)
    _ts_wid: memoryview = field(init=False)

    def __post_init__(self) -> None:
        self.__init_attributes(self._configs, self._main_tools)

        self._procs_status = self.cfgMetrics.procs_status.view.cast("q")
        self._main_status = self.cfgMetrics.main_status.view.cast("q")

        self._ts_safe_lag = self._log_stream.ring_buf.safe_lag
        self._ts_cell_amount = self._log_stream.ring_buf.cell_amount
        self._ts_data = self._log_stream.ring_buf.data.view
        self._ts_data_size = self._log_stream.ring_buf.data_size
        self._ts_data_header = self._log_stream.ring_buf.data_header.view.cast(
            "q"
        )
        self._ts_rid = self._log_stream.ring_buf.reader_id.view.cast("q")
        self._ts_wid = self._log_stream.ring_buf.writer_id.view.cast("q")

    @final
    def __init_attributes(
        self,
        configs: list[cfg.Configuration],
        main_tools: list[Event | Semaphore],
    ) -> None:
        objs: list[cfg.Configuration | Event | Semaphore] = configs + main_tools
        for obj in objs:
            for attr_name, attr_type in Base.__annotations__.items():
                if issubclass(attr_type.__class__, GenericAlias):
                    continue

                if isinstance(obj, attr_type):
                    setattr(self, attr_name, obj)
                    if isinstance(obj, cfg.SharedMemorySegments):
                        self.__bind_shm_segments(obj)
                    break

    @final
    def __bind_shm_segments(self, cfg: cfg.SharedMemorySegments) -> None:
        buf: memoryview = self._shm_buf[self._segments[cfg.__class__.__name__]]
        for attr_name in cfg.__slots__:
            attr_val = getattr(cfg, attr_name)
            if isinstance(attr_val, Segment):
                attr_val.view = buf[slice(*attr_val.offset)]
            elif isinstance(attr_val, RingBuf):
                for ring_attr_name in attr_val.__slots__:
                    if hasattr(attr_val, ring_attr_name):
                        ring_attr_val = getattr(attr_val, ring_attr_name)
                        if isinstance(ring_attr_val, Segment):
                            ring_attr_val.view = buf[
                                slice(*ring_attr_val.offset)
                            ]
