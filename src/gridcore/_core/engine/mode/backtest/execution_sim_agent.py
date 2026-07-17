import time

from .... import constant as c
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ....utils.monitoring.status_codes import StatusCodes as scs
from ...base.base_execution import Execution
from .execution_utils.data_prepper import DataPrepper
from .execution_utils.matching_engine import MatchingEngine
from .execution_utils.trade_manager import TradeManager
from .rest_sim_agent import RestSimAgent


class ExecutionAgent(Execution):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager=manager)

        self.rest = RestSimAgent(self.symbol, manager.cfgBacktesting)
        self.tm = TradeManager(converter=self.con)
        self.prepper = DataPrepper(
            symbol=self.symbol,
            startDate=manager.cfgBacktesting.backtest_start_date,
            endDate=manager.cfgBacktesting.backtest_end_date,
            priceMult=self.con.priceMult,
        )
        self.me = MatchingEngine(self.con, self.tm, self.prepper)
        self.con.init_session(
            startBalance=self.rest.get_balance(),
            minOrderSize=self.rest.get_min_order_size_usdt(),
            takerCommission=self.rest.get_commission(is_maker=False),
            makerCommission=self.rest.get_commission(is_maker=True),
        )
        self.temp = 0

    def alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        while (self.logic_complete[0] == 0) and (
            (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0])
        ):
            time.sleep(0)

    def pre_executed_actions(self) -> None:
        pass

    def executed_action(self) -> None:
        pass

    def pre_execute_actions(self) -> None:
        pass

    def execute_action(
        self, nPrice: int, time_get_signal: int, orderParam: int
    ) -> None:
        _ = self.con
        # - - -
        timestamp = time_get_signal + _.latencyMs
        if self.start_matching(timestamp):
            if (qty := _.nominalEntryNqtyWithLeverage) is not None:
                nQty: int = _.entryNqtyWithLeverage(nPrice, qty)
                is_market: bool = bool(orderParam & c.OF_MARKET)
                if not is_market:
                    _.lockedNbalance = _.to_nMargin(nPrice, nQty)

                self.tm.set_active_order(nPrice, nQty, timestamp, orderParam)
                self.temp += 1
            else:
                self.set_proc_sc(code=scs.QTY_LESS_LIMIT)

    def start_matching(self, timestamp: int | None) -> bool:
        try:
            return False
        except RuntimeError:
            self.set_proc_sc(code=scs.LOSS_MORE_LIMIT)
            print(self.stat(), flush=True)
            self.tm.final_action()
            return False

    def post_check_bufs(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        pass

    def stat(self) -> str:
        return (
            f"Balance: {self.con.nBalance / self.con.scale} \n"
            f"Locked Balance: {self.con.lockedNbalance / self.con.scale} \n"
            f"Unrealized PNL: {self.con.unrealizedNpnl / self.con.scale} \n"
            f"Long Unrealized PNL: {self.con.longUnrealizedNpnl / self.con.scale} \n"
            f"Short Unrealized PNL: {self.con.shortUnrealizedNpnl / self.con.scale} \n"
            f"Long Open Qty: {self.con.longNqty / self.con.scale} \n"
            f"Short Open Qty: {self.con.shortNqty / self.con.scale} \n"
            f"Count Orders in History: {self.con.last_order_id} \n"
            f"Count Active Orders: {self.tm.aoWRow[0]} \n"
            f"Count Open Positions: {self.temp}"
        )

    def post_final_action(self) -> None:
        self.tm.final_action()
        print(self.stat(), flush=True)


@manager_office()
def run_execution_sim(**kwargs):
    agent = ExecutionAgent(manager=kwargs["manager"])
    agent.run_execution_engine()
