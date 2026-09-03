import time
from dataclasses import dataclass
from typing import override

from imprint.core.exchange.sim import ExchangeSim
from imprint.core.pipeline.executing.base import Base


@dataclass(slots=True)
class Backtest(Base[ExchangeSim]):
    @override
    def init_session(self) -> None:
        self.account: ExchangeSim = ExchangeSim(self.manager)
        self.con.init_session(
            nBalance=self.account.nBalance,
            lockedNbalance=self.account.lockedNbalance,
            availableNbalance=self.account.availableNbalance,
            longNqty=self.account.longNqty,
            longEntryNprice=self.account.longEntryNprice,
            shortNqty=self.account.shortNqty,
            shortEntryNprice=self.account.shortEntryNprice,
            unrealizedNpnl=self.account.unrealizedNpnl,
            longUnrealizedNpnl=self.account.longUnrealizedNpnl,
            shortUnrealizedNpnl=self.account.shortUnrealizedNpnl,
        )

    @override
    def alarm_clock(
        self,
        WB_1: memoryview,
        RB_1: memoryview,
        WB_2: memoryview,
        RB_2: memoryview,
    ) -> None:
        matching = False
        if self.trade_readed_time[0] > self.account.trade_readed_time[0]:
            matching = True
        if (WB_1[0] != RB_1[0]) or (WB_2[0] != RB_2[0]):
            return
        if matching:
            self.account.start(self.trade_readed_time[0])

        time.sleep(0)

    @override
    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        timestamp = time_get_signal + self.con.latency
        while timestamp > self.account.trade_readed_time[0]:
            self.account.start(timestamp)
            self._check_user_data_buf()

        self.readed_timestamp: int = self.account.trade_readed_time[0]

    @override
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        get_data: memoryview = user_data_raw_buf.cast("q")
        timestamp: int = get_data[0]
        order_param: int = get_data[1]
        order_id: int = get_data[2]
        nPrice: int = get_data[3]
        nQty: int = get_data[4]
        nCommission: int = get_data[5]
        nMAE: int = get_data[6]
        nMFE: int = get_data[7]

        self.executor.action_for_getted_executed_order(
            timestamp, order_param, order_id, nPrice, nQty, nCommission
        )
        self.con.update_orders_history(
            timestamp,
            order_param,
            order_id,
            nPrice,
            nQty,
            nCommission,
            nMAE,
            nMFE,
        )

    @override
    def post_final_action(self) -> None:
        max_timestamp = 9_999_999_999_999
        while self.account.trade_readed_time[0] < max_timestamp:
            self.account.start(max_timestamp)
            self._check_user_data_buf()
            if (
                self.account.prepper.complete
                and self.account.prepper.dfmRid[0]
                == self.account.prepper.dfmWid[0]
            ):
                break

        self.con.final_action()
        self.account.final_action()
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
                f"Count Active Orders: {self.account.obRow[0]} \n"
                f"Count Open Positions: {self.count_open_positions[0]}"
            )
        )
