from abc import ABC, abstractmethod

from ...ipc import NodeManager
from .backtest import Backtest as BacktestAgent
from .live import Live as LiveAgent


class Router(BacktestAgent, LiveAgent, ABC):
    def __init__(self, manager: NodeManager, **kwargs):
        if manager.cfgSetup.backtesting:
            BacktestAgent.__init__(self, manager)
            self._execution = BacktestAgent
        else:
            LiveAgent.__init__(self, manager, kwargs["execution_event"])
            self._execution = LiveAgent

    def _alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        self._execution._alarm_clock(self, WB_1, RB_1, WB_2, RB_2)

    def _pre_execute_signal_action(self, time_get_signal: int) -> None:
        self._execution._pre_execute_signal_action(self, time_get_signal)

    def send_order(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        self._execution.send_order(
            self, timestamp, order_param, client_order_id, nPrice, nQty
        )

    def _preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        self._execution._preppare_user_data(self, user_data_raw_buf)

    @abstractmethod
    def action_for_getted_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        pass

    @abstractmethod
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

    def _final_actions(self) -> None:
        self._execution._final_actions(self)

    def _post_final_action(self) -> None:
        self._execution._post_final_action(self)
