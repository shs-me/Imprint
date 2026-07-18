import time

from .... import constant as c
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ....utils.monitoring.status_codes import StatusCodes as scs
from ...base.base_execution import Execution
from .matching_engine import MatchingEngine
from .rest_sim_agent import RestSimAgent


class ExecutionAgent(Execution):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager=manager)

        self.rest = RestSimAgent(self.symbol, manager.cfgBacktesting)
        self.me = MatchingEngine()
        self.con.init_session(
            startBalance=self.rest.get_balance(),
            minOrderSize=self.rest.get_min_order_size_usdt(),
            takerCommission=self.rest.get_commission(is_maker=False),
            makerCommission=self.rest.get_commission(is_maker=True),
        )

    def alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        while (self.logic_complete[0] == 0) and (
            (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0])
        ):
            time.sleep(0)

    def pre_execute_signal_action(self) -> None:
        pass

    def execute_signal(
        self, nPrice: int, time_get_signal: int, orderParam: int
    ) -> None:
        pass

    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        pass

    def post_check_bufs(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        pass


@manager_office()
def run_execution_sim(**kwargs):
    agent = ExecutionAgent(manager=kwargs["manager"])
    agent.run_execution_engine()
