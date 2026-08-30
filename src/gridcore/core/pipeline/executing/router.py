from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

from .backtest import Backtest as BacktestAgent
from .live import Live as LiveAgent


@dataclass(slots=True)
class Router(BacktestAgent, LiveAgent, ABC):
    is_backtesting: bool = field(init=False)
    _execution_type: type[BacktestAgent | LiveAgent] = field(init=False)

    @abstractmethod
    def __post_init__(self):
        self.is_backtesting = self._manager.cfgSetup.backtesting
        if self.is_backtesting:
            BacktestAgent.__post_init__(self)
            self._execution_type = BacktestAgent
        else:
            LiveAgent.__post_init__(self)
            self._execution_type = LiveAgent

    @final
    @override
    def _alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        self._execution_type._alarm_clock(self, WB_1, RB_1, WB_2, RB_2)

    @final
    @override
    def _pre_execute_signal_action(self, time_get_signal: int) -> None:
        self._execution_type._pre_execute_signal_action(self, time_get_signal)

    @final
    @override
    def _preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        self._execution_type._preppare_user_data(self, user_data_raw_buf)

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

    @final
    @override
    def _post_final_action(self) -> None:
        self._execution_type._post_final_action(self)
