from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import override

from imprint._core.account import Account
from imprint._core.ipc import NodeManager
from imprint._core.pipeline.executing.backtest import Backtest as BacktestAgent
from imprint._core.pipeline.executing.live import Live as LiveAgent
from imprint._core.settings import ExecutionProtocol, SendOrderMethodSignature


@dataclass
class Router(ExecutionProtocol, ABC):
    _manager: NodeManager
    _execution_event: Event

    _executer: BacktestAgent | LiveAgent = field(init=False)

    is_backtesting: bool = field(init=False)
    count_open_positions: memoryview = field(init=False)
    account: Account = field(init=False)
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
        self.account = self._executer.account

    @abstractmethod
    @override
    def on_signal(
        self,
        signal_id: int,
        time_get_signal: int,
        order_param: int,
        nPrice: int,
        nQty: int,
    ) -> None: ...

    @abstractmethod
    @override
    def on_filled_order(
        self,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        order_id: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None: ...

    @abstractmethod
    @override
    def on_canceled_order(
        self,
        timestamp: int,
        is_long: bool,
        is_buy: bool,
        order_id: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
        nCommission: int,
    ) -> None: ...
