import importlib
from abc import ABC, abstractmethod
from multiprocessing.synchronize import Event

from ...settings import ExecutionProc
from ...utils.handlers import supervisor
from ...utils.monitoring.agent_manager import AgentManager
from ..mode.backtest.execution_sim_agent import ExecutionAgent as SimExecAgent
from ..mode.real.execution_agent import ExecutionAgent as RealExecAgent


class Execution(SimExecAgent, RealExecAgent, ABC):
    def __init__(self, manager: AgentManager, **kwargs):
        if manager.cfgSetup.backtesting:
            SimExecAgent.__init__(self, manager)
            self._execution = SimExecAgent
        else:
            RealExecAgent.__init__(self, manager, kwargs["execution_event"])
            self._execution = RealExecAgent

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


def run(manager: AgentManager, **kwargs) -> None:
    m_name = manager.cfgSetup.execution_module
    c_name = manager.cfgSetup.execution_class_name
    execution: type[Execution] = getattr(importlib.import_module(m_name), c_name)
    agent = execution(manager, **kwargs)
    agent._run_execution_engine()


@supervisor()
def run_execution_sim(proc: ExecutionProc = ExecutionProc(), **kwargs):
    """Supervisor-wrapped entry point for simulated Execution process."""

    run(manager=kwargs["manager"])


@supervisor()
def run_execution(
    execution_event: Event, proc: ExecutionProc = ExecutionProc(), **kwargs
):
    """Supervisor-wrapped entry point for live Execution process."""

    run(manager=kwargs["manager"], execution_event=execution_event)
