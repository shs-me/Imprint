import time

from .... import constant as c
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ...base.base_execution import Execution
from .account_manager import AccountManager


class ExecutionAgent(Execution):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager=manager)

        self.acm: AccountManager = AccountManager(manager)
        self.con.init_session(
            nBalance=self.acm.nBalance,
            lockedNbalance=self.acm.lockedNbalance,
            availableNbalance=self.acm.availableNbalance,
            longNqty=self.acm.longNqty,
            longEntryNprice=self.acm.longEntryNprice,
            shortNqty=self.acm.shortNqty,
            shortEntryNprice=self.acm.shortEntryNprice,
            unrealizedNpnl=self.acm.unrealizedNpnl,
            longUnrealizedNpnl=self.acm.longUnrealizedNpnl,
            shortUnrealizedNpnl=self.acm.shortUnrealizedNpnl,
        )
        self.count_open_position: int = 0

    def alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        matching = False
        while self.logic_complete[0] == 0:
            if self.trade_readed_time[0] > self.acm.trade_readed_time[0]:
                matching = True
            if (WB_1[0] != RB_1[0]) or (WB_2[0] != RB_2[0]):
                break
            if matching:
                self.acm.start(self.trade_readed_time[0])

            time.sleep(0)

    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        self.acm.start(time_get_signal + self.con.latency)

    def execute_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        if self.con.is_averaging(order_param):
            return

        self.acm.send_order(
            timestamp=time_get_signal,
            order_param=order_param,
            client_order_id=1,
            nPrice=nPrice,
            nQty=nQty,
        )
        self.count_open_position += 1

    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        get_data: memoryview = user_data_raw_buf.cast("q")
        timestamp: int = get_data[0]
        order_param: int = get_data[1]
        order_id: int = get_data[2]
        nPrice: int = get_data[3]
        nQty: int = get_data[4]
        nCommission: int = get_data[5]

        is_long, is_buy = (bool(order_param & c.OF_LONG), bool(order_param & c.OF_BUY))
        if bool(order_param & c.OF_FILLED):
            is_open = (is_long and is_buy) or (not is_long and not is_buy)
            if is_open:
                tp_sl_timestamp: int = timestamp + self.con.latency

                tp_nPrice: int = self.con.TPdevNprice(nPrice, is_long)
                tp_order_param: int = 0
                tp_order_param |= c.OF_LONG if is_long else c.OF_SHORT
                tp_order_param |= c.OF_SELL if is_buy else c.OF_BUY
                tp_order_param |= c.OF_LIMIT | c.OF_NEW | c.OF_OCO
                self.acm.send_order(
                    tp_sl_timestamp, tp_order_param, order_id, tp_nPrice, nQty
                )

                sl_nPrice: int = self.con.SLdevNprice(nPrice, is_long)
                sl_order_param: int = 0
                sl_order_param |= c.OF_LONG if is_long else c.OF_SHORT
                sl_order_param |= c.OF_SELL if is_buy else c.OF_BUY
                sl_order_param |= c.OF_MARKET_TRIGER | c.OF_NEW | c.OF_OCO
                self.acm.send_order(
                    tp_sl_timestamp, sl_order_param, order_id, sl_nPrice, nQty
                )

        elif bool(order_param & c.OF_CANCELED):
            pass

        self.con.update_orders_history(
            timestamp, order_param, order_id, nPrice, nQty, nCommission
        )

    def post_check_bufs(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        pass

    def post_final_action(self) -> None:
        if self.trade_readed_time[0] > self.acm.trade_readed_time[0]:
            self.acm.start(self.trade_readed_time[0])

        self.check_user_data_buf()
        self.con.final_action()
        self.manager.set_text(
            (
                f"Balance: {self.con.nBalance / self.con.scale} \n"
                f"Locked Balance: {self.con.lockedNbalance / self.con.scale} \n"
                f"Unrealized PNL: {self.con.unrealizedNpnl / self.con.scale} \n"
                f"Long Unrealized PNL: {self.con.longUnrealizedNpnl / self.con.scale} \n"
                f"Short Unrealized PNL: {self.con.shortUnrealizedNpnl / self.con.scale} \n"
                f"Long Open Qty: {self.con._longNqty[0] / self.con.qtyMult} \n"
                f"Short Open Qty: {self.con._shortNqty[0] / self.con.qtyMult} \n"
                f"Count Orders in History: {self.con.ohWid[0]} \n"
                f"Count Active Orders: {self.acm.obRow[0]} \n"
                f"Count Open Positions: {self.count_open_position}"
            )
        )


@manager_office()
def run_execution_sim(**kwargs):
    agent = ExecutionAgent(manager=kwargs["manager"])
    agent.run_execution_engine()
