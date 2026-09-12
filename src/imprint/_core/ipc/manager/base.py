"""Abstract shared memory segment binding manager.

This module defines the Base abstract manager which binds shared memory slices to
specific fields in configuration objects using dataclass annotations. It maps status
buffers, ring buffers, log streams, and multi-process events to simplify IPC.
"""

from abc import ABC
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event, Semaphore
from types import GenericAlias
from typing import final

from imprint._core import configs as cfg
from imprint._core.configs import RingBuf, Segment


@dataclass(slots=True)
class Base(ABC):
    """Base manager binding shared memory slice references to configuration objects.

    Provides core routines to scan system configuration classes, resolve their
    SharedMemory slice specifications, and dynamically bind sliced memoryviews
    to Segment and RingBuf fields.

    Parameters
    ----------
    _segments : dict[str, slice]
        Mappings of Configuration class names to their respective slices within
        the main shared memory block.
    _shm_buf : memoryview
        The full memoryview buffer of the system's SharedMemory.
    _configs : list[cfg.Configuration]
        Instantiated Configuration instances representing state structures.
    _main_tools : list[Event | Semaphore]
        Synchronization tools including signaling events and status semaphores.

    Attributes
    ----------
    cfgSetup : cfg.Setup
        Setup parameters and environment configurations.
    cfgAccount : cfg.Account
        Trading account state/margin configurations.
    cfgConnector : cfg.Connector
        API Connection/REST endpoint configurations.
    cfgRiskManagement : cfg.RiskManagement
        Risk parameters and balance limits.
    cfgCoin : cfg.Coin
        Active asset specifications.
    cfgFootprint : cfg.Footprint
        Footprint chart dimension/row/column parameters.
    cfgMetrics : cfg.Metrics
        Process status codes and health buffers.
    cfgMarketDataStream : cfg.MarketDataStream
        Shared memory layouts for market data streams.
    cfgUserDataStream : cfg.UserDataStream
        Shared memory layouts for user data streams.
    cfgOrderStream : cfg.OrderStream
        Shared memory layouts for active orders.
    cfgSignalStream : cfg.SignalStream
        Shared memory layouts for trading signals.
    _log_stream : cfg.LogStream
        Ring buffer segment dedicated to IPC logging logs.
    _sc_sem : Semaphore
        Semaphore to signal task status/event updates.
    _general_event : Event
        General process synchronization event.
    _procs_status : memoryview
        Process-level status integer array (cast to int64/'q').
    _main_status : memoryview
        Host-level process status integer array (cast to int64/'q').
    """

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
    cfgMarketDataStream: cfg.MarketDataStream = field(init=False)
    cfgUserDataStream: cfg.UserDataStream = field(init=False)
    cfgOrderStream: cfg.OrderStream = field(init=False)
    cfgSignalStream: cfg.SignalStream = field(init=False)

    _log_stream: cfg.LogStream = field(init=False)
    _sc_sem: Semaphore = field(init=False)
    _general_event: Event = field(init=False)

    _procs_status: memoryview = field(init=False)
    _main_status: memoryview = field(init=False)

    def __post_init__(self) -> None:
        """Initialize configurations, synchronize attributes, and cast status buffer views."""
        self.__init_attributes(self._configs, self._main_tools)

        self._procs_status = self.cfgMetrics.procs_status.view.cast("q")
        self._main_status = self.cfgMetrics.main_status.view.cast("q")

    @final
    def __init_attributes(
        self,
        configs: list[cfg.Configuration],
        main_tools: list[Event | Semaphore],
    ) -> None:
        """Identify, filter, and bind configuration components to Base attributes.

        Parameters
        ----------
        configs : list[cfg.Configuration]
            List of configuration items containing data structure fields.
        main_tools : list[Event | Semaphore]
            Multi-processing sync instances.
        """
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
        """Bind memoryview sub-slices to segment structures in a configuration.

        Parameters
        ----------
        cfg : cfg.SharedMemorySegments
            The segment configurations to associate with target memory slices.
        """
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

                attr_val.post_init()
