from abc import ABC
from dataclasses import dataclass, field
from typing import final

from imprint._core.configs import MarketDataStream, OrderStream, UserDataStream
from imprint._core.ipc import NodeManager


@dataclass(slots=True)
class Base(ABC):
    manager: NodeManager

    symbol: str = field(init=False)
    mds: MarketDataStream = field(init=False)
    uds: UserDataStream = field(init=False)
    os: OrderStream = field(init=False)

    def __post_init__(self) -> None:
        self.symbol = self.manager.cfgCoin.symbol
        self.mds = self.manager.cfgMarketDataStream
        self.uds = self.manager.cfgUserDataStream
        self.os = self.manager.cfgOrderStream

    @final
    def final_actions(self) -> None:
        self.manager.set_log(" ")
