import time
from abc import ABC, abstractmethod

from ...ipc import NodeManager
from .base import Base
from .simulation import ExchangeSim


class Backtest(Base, ABC):
    def __init__(self, manager: NodeManager) -> None:
        Base.__init__(self, manager=manager)

        self.acm = ExchangeSim(manager)
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

    @abstractmethod
    def _alarm_clock(
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

    @abstractmethod
    def _pre_execute_signal_action(self, time_get_signal: int) -> None:
        timestamp = time_get_signal + self.con.latency
        while timestamp > self.acm.trade_readed_time[0]:
            self.acm.start(timestamp)
            self._check_user_data_buf()

        self.readed_timestamp = self.acm.trade_readed_time[0]

    @abstractmethod
    def action_for_getted_signal(
        self, time_get_signal: int, order_param: int, nPrice: int, nQty: int
    ) -> None:
        pass

    @abstractmethod
    def _preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        get_data: memoryview = user_data_raw_buf.cast("q")
        timestamp: int = get_data[0]
        order_param: int = get_data[1]
        order_id: int = get_data[2]
        nPrice: int = get_data[3]
        nQty: int = get_data[4]
        nCommission: int = get_data[5]
        nMAE: int = get_data[6]
        nMFE: int = get_data[7]

        self.action_for_getted_executed_order(
            timestamp, order_param, order_id, nPrice, nQty, nCommission
        )
        self.con.update_orders_history(
            timestamp, order_param, order_id, nPrice, nQty, nCommission, nMAE, nMFE
        )

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
    def _final_actions(self) -> None:
        max_timestamp = 9_999_999_999_999
        while self.acm.trade_readed_time[0] < max_timestamp:
            self.acm.start(max_timestamp)
            self._check_user_data_buf()
            if (
                self.acm.prepper.complete
                and self.acm.prepper.dfmRid[0] == self.acm.prepper.dfmWid[0]
            ):
                break

        self._post_final_action()

    @abstractmethod
    def _post_final_action(self) -> None:
        self.con.final_action()
        self.acm.final_action()
        self.manager.set_text(
            (
                f"Balance: {self.con.nBalance / self.con.scale}. Locked Balance: {self.con.lockedNbalance / self.con.scale}"
            )
        )
