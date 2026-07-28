"""Live order execution process agent."""

from multiprocessing.synchronize import Event

from ....utils.handlers import supervisor
from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_execution import Execution
from ...mode.real.rest_agent import RestAgent


class ExecutionAgent(Execution):
    """Live Execution engine managing REST interactions with exchange."""

    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager=manager)

        self.execution_event: Event = execution_event

        self.rest: RestAgent = RestAgent(symbol=self.symbol)

    def alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        """Blocks process on execution_event when ring buffers are drained."""

        if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
            self.execution_event.clear()
            if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
                self.execution_event.wait(timeout=60)

    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        pass

    def execute_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        pass

    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        pass

    def post_check_bufs(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        pass

    def post_final_action(self) -> None:
        pass


@supervisor()
def run_execution(execution_event: Event, **kwargs):
    """Supervisor-wrapped entry point for live Execution process."""

    agent = ExecutionAgent(manager=kwargs["manager"], execution_event=execution_event)
    agent.run_execution_engine()
