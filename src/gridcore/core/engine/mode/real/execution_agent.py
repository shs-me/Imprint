"""Live order execution process agent."""

from abc import ABC, abstractmethod
from multiprocessing.synchronize import Event

from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_execution import BaseExecution
from ...mode.real.rest_agent import RestAgent


class ExecutionAgent(BaseExecution, ABC):
    """Live Execution engine managing REST interactions with exchange."""

    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        BaseExecution.__init__(self, manager=manager)

        self.execution_event: Event = execution_event

        self.rest: RestAgent = RestAgent(
            symbol=self.symbol, connector=manager.cfgConnector
        )

    @abstractmethod
    def _alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        """Blocks process on execution_event when ring buffers are drained."""

        if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
            self.execution_event.clear()
            if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
                self.execution_event.wait(timeout=60)

    @abstractmethod
    def _pre_execute_signal_action(self, time_get_signal: int) -> None:
        pass

    @abstractmethod
    def action_for_getted_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        pass

    @abstractmethod
    def _preppare_user_data(self, user_data_raw_buf: memoryview) -> None:

        data = user_data_raw_buf.cast("q")
        event_type = data[1]

        if event_type == 1:
            timestamp: int = data[0]
            order_param: int = data[2]
            order_id: int = data[3]
            nPrice: int = data[4]
            nQty: int = data[5]
            nCommission: int = data[6]

            self.action_for_getted_executed_order(
                timestamp, order_param, order_id, nPrice, nQty, nCommission
            )
            self.con.update_orders_history(
                timestamp, order_param, order_id, nPrice, nQty, nCommission, 0, 0
            )

        elif event_type == 2:
            new_balance = data[7]

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

    @abstractmethod
    def _post_final_action(self) -> None:
        pass
