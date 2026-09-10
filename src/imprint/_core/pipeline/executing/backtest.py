import time
from dataclasses import dataclass, field
from typing import override

from imprint._core import constant as c
from imprint._core.exchange_sim import ExchangeSim
from imprint._core.pipeline.executing.base import Base


@dataclass(slots=True)
class Backtest(Base):
    exchange_sim: ExchangeSim = field(init=False)

    @override
    def child_post_init(self) -> None:
        self.exchange_sim = ExchangeSim(self.manager)

        self.account.nBalance = self.exchange_sim.nBalance
        self.account.lockedNbalance = self.exchange_sim.lockedNbalance
        self.account.availableNbalance = self.exchange_sim.availableNbalance

    @override
    def alarm_clock(
        self,
        WB_1: memoryview,
        RB_1: memoryview,
        WB_2: memoryview,
        RB_2: memoryview,
    ) -> None:
        matching = False
        if self.trade_read_time[0] > self.exchange_sim.trade_read_time[0]:
            matching = True
        if (WB_1[0] != RB_1[0]) or (WB_2[0] != RB_2[0]):
            return
        if matching:
            self.exchange_sim.start(self.trade_read_time[0])

        time.sleep(0.001)

    @override
    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        timestamp = time_get_signal + self.exchange_sim.latency
        while timestamp > self.exchange_sim.trade_read_time[0]:
            self.exchange_sim.start(timestamp)
            self._check_user_data_buf()

        self.readed_timestamp: int = self.exchange_sim.trade_read_time[0]

    @override
    def send_order(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        timestamp = timestamp + self.exchange_sim.latency
        Base.send_order(
            self, timestamp, order_param, client_order_id, nPrice, nQty
        )
        self.exchange_sim.lock_balance(nPrice, nQty, order_param)

    @override
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        get_data: memoryview = user_data_raw_buf.cast("q")
        timestamp: int = get_data[c.TP_timestamp]
        order_param: int = get_data[c.TP_order_param]
        order_id: int = get_data[c.TP_order_id]
        client_order_id: int = get_data[c.TP_client_order_id]
        nPrice: int = get_data[c.TP_nPrice]
        nQty: int = get_data[c.TP_nQty]
        nCommission: int = get_data[c.TP_nCommission]
        nMAE: int = get_data[c.TP_nMAE]
        nMFE: int = get_data[c.TP_nMFE]

        self.exchange_sim.update_orders_history(
            timestamp=timestamp,
            order_param=order_param,
            order_id=order_id,
            client_order_id=client_order_id,
            nPrice=nPrice,
            nQty=nQty,
            nCommission=nCommission,
            nMAE=nMAE,
            nMFE=nMFE,
        )
        self.on_order_update(
            timestamp=timestamp,
            order_param=order_param,
            order_id=order_id,
            client_order_id=client_order_id,
            nPrice=nPrice,
            nQty=nQty,
            nCommission=nCommission,
        )

    @override
    def post_final_action(self) -> None:
        _ = self.exchange_sim
        # - - -
        self.exchange_sim.final_action(self.trade_read_time[0])
        self.manager.set_log(
            f"Balance: {_.nBalance[0] / _.scale_mult} \n"
            + f"Locked Balance: {_.lockedNbalance[0] / _.scale_mult} \n"
            + f"Unrealized PNL: {_.unrealizedNpnl[0] / _.scale_mult} \n"
            + f"Long Unrealized PNL: {_.longUnrealizedNpnl[0] / _.scale_mult} \n"
            + f"Short Unrealized PNL: {_.shortUnrealizedNpnl[0] / _.scale_mult} \n"
            + f"Long Open Qty: {_.longNqty[0] / _.qty_mult} \n"
            + f"Short Open Qty: {_.shortNqty[0] / _.qty_mult} \n"
            + f"Count Orders in History: {_.ohWid[0]} \n"
            + f"Count Active Orders: {_.obRow[0]} \n"
            + f"Count Open Positions: {self.count_open_positions[0]}"
        )
