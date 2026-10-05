from abc import ABC
from dataclasses import dataclass, field
from typing import final

from imprint._core.configs import (
    MarketDataGapStream,
    MarketDataStream,
    OrderStream,
    UserDataStream,
)
from imprint._core.ipc import NodeManager


@dataclass(slots=True)
class Base(ABC):
    """Abstract base class for streaming pipeline nodes.

    Initializes configuration proxies and manages node lifecycle state through an IPC NodeManager.

    Parameters
    ----------
    manager : NodeManager
        Inter-process communication and configuration manager instance.

    Attributes
    ----------
    manager : NodeManager
        Inter-process communication and configuration manager instance.
    symbol : str
        Trading pair symbol resolved from coin configuration.
    mds : MarketDataStream
        Market data stream configuration parameters.
    mdgs : MarketDataGapStream
        Market data gap detection and recovery stream configuration.
    uds : UserDataStream
        User private data stream configuration parameters.
    os : OrderStream
        Order execution and management stream configuration.
    """

    manager: NodeManager

    symbol: str = field(init=False)
    mds: MarketDataStream = field(init=False)
    mdgs: MarketDataGapStream = field(init=False)
    uds: UserDataStream = field(init=False)
    os: OrderStream = field(init=False)

    @final
    def __post_init__(self) -> None:
        """Initialize configuration bindings and execute post-initialization hooks."""
        self.symbol = self.manager.cfgCoin.symbol
        self.mds = self.manager.cfgMarketDataStream
        self.mdgs = self.manager.cfgMarketDataGapStream
        self.uds = self.manager.cfgUserDataStream
        self.os = self.manager.cfgOrderStream
        self.post_init()

    def post_init(self) -> None:
        """Perform subclass-specific initialization logic after configuration bindings."""

    @final
    def final_actions(self) -> None:
        """Execute cleanup actions and clear active logs upon stream termination."""
        self.manager.set_log(" ")
