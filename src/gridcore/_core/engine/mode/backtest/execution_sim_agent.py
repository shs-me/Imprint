import time

from .... import constant as c
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ...base.base_execution import Execution
from .matching_engine import MatchingEngine
from .rest_sim_agent import RestSimAgent


class ExecutionAgent(Execution):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager=manager)

        self.rest = RestSimAgent(self.symbol, manager.cfgBacktesting)
        self.me = MatchingEngine(manager)
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
            if self.trade_readed_time[0] > self.me.trade_readed_time[0]:
                self.me.matching(self.trade_readed_time[0])

            time.sleep(0)

    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        self.me.matching(time_get_signal + self.con.latency)

    def execute_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        self.con.lockedNbalance = self.con.to_nMargin(nPrice, nQty)
        self.me.update_order_book(
            timestamp=time_get_signal + self.con.latency,
            order_param=order_param,
            nPrice=nPrice,
            nQty=nQty,
        )

    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        get_data: memoryview = user_data_raw_buf.cast("q")
        timestamp: int = get_data[0]
        order_param: int = get_data[0]
        order_id: int = get_data[0]
        nPrice: int = get_data[0]
        nQty: int = get_data[0]

        if bool(order_param & c.OF_FILLED):
            nCommission = self.con.to_nCommission(nQty, bool(order_param & c.OF_LIMIT))
            is_long, is_buy = (
                bool(order_param & c.OF_LONG),
                bool(order_param & c.OF_BUY),
            )
            is_open = (is_long and is_buy) or (not is_long and not is_buy)
            self.tm.update_position(nPrice, nQty, nCommission, is_open, is_long)
        else:
            nCommission = 0

        self.tm.update_orders_history(
            timestamp, order_param, order_id, nPrice, nQty, nCommission
        )

    def post_check_bufs(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        pass

    def post_final_action(self) -> None:
        pass


@manager_office()
def run_execution_sim(**kwargs):
    agent = ExecutionAgent(manager=kwargs["manager"])
    agent.run_execution_engine()
