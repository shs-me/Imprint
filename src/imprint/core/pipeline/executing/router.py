from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import override

from imprint.core.exchange.account import AccountConverter
from imprint.core.ipc import NodeManager
from imprint.core.pipeline.executing.backtest import Backtest as BacktestAgent
from imprint.core.pipeline.executing.base import (
    ExecutionProtocol,
    SendOrderMethodSignature,
)
from imprint.core.pipeline.executing.live import Live as LiveAgent


@dataclass
class Router(ExecutionProtocol, ABC):
    _manager: NodeManager
    _execution_event: Event

    _executer: BacktestAgent | LiveAgent = field(init=False)

    is_backtesting: bool = field(init=False)
    count_open_positions: memoryview = field(init=False)
    con: AccountConverter = field(init=False)
    send_order: SendOrderMethodSignature = field(init=False)

    def __post_init__(self):
        self.is_backtesting = self._manager.cfgSetup.backtesting
        if self.is_backtesting:
            self._executer = BacktestAgent(self._manager, self)
        else:
            self._executer = LiveAgent(
                self._manager, self, self._execution_event
            )

        self.count_open_positions = self._executer.count_open_positions
        self.send_order = self._executer.send_order
        self.con = self._executer.con

    @abstractmethod
    @override
    def action_for_getted_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        pass

    @abstractmethod
    @override
    def action_for_getted_executed_order(
        self,
        timestamp: int,
        order_param: int,
        order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None:
        pass
