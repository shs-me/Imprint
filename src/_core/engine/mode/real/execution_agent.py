from multiprocessing.synchronize import Event

from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ...base.base_execution import Execution
from ...base.utils.tm_con import TradeConverter
from ...mode.real.rest_agent import RestAgent


class ExecutionAgent(Execution):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager=manager)

        self.execution_event = execution_event

        self.rest = RestAgent(symbol=self.symbol)
        self.con = TradeConverter(
            trade_param=self.trade_par, cfgStrategy=manager.cfgStrategy
        )
        self.con.init_session(
            startBalance=self.rest.get_balance(),
            minOrderSize=self.rest.get_min_order_size_usdt(),
            takerCommission=self.rest.get_commission(is_maker=False),
            makerCommission=self.rest.get_commission(is_maker=True),
        )

    def alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
            self.execution_event.clear()
            if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
                self.execution_event.wait(timeout=60)

    def signal_prepare(
        self, nPrice: int, time_get_signal: int, orderParam: int
    ) -> None:
        self.rest.send_new_order()

    def data_prepare(self) -> None:
        pass


@manager_office()
def run_execution(execution_event: Event, **kwargs):
    agent = ExecutionAgent(manager=kwargs["manager"], execution_event=execution_event)
    agent.run_execution_engine()
