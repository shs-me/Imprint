import time
from dataclasses import dataclass, field
from typing import override

from imprint._core import constant as c
from imprint._core.exchange_sim import ExchangeSim
from imprint._core.pipeline.executing.base import Base


@dataclass(slots=True)
class Backtest(Base):
    """Executes backtesting simulation pipelines, coordinating exchange state and order lifecycles.

    Parameters
    ----------
    manager : NodeManager
        Manager coordinating process states, tasks, and communication streams.
    executor : ExecutionProtocol
        Protocol implementation handling orders, signals, and execution callbacks.

    Attributes
    ----------
    exchange_sim : ExchangeSim
        Simulation engine modeling order matching, latency, and account balances.
    """

    exchange_sim: ExchangeSim = field(init=False)

    @override
    def __post_init__(self) -> None:
        """Initialize simulation exchange state and sync account balances."""
        Base.__post_init__(self)

        self.exchange_sim = ExchangeSim(self.manager)
        self.account.nBalance = self.exchange_sim.nBalance
        self.account.lockedNbalance = self.exchange_sim.lockedNbalance
        self.account.availableNbalance = self.exchange_sim.availableNbalance

    @override
    def reset(self) -> None:
        Base.reset(self)

        self.exchange_sim.reset()

    @override
    def alarm_clock(
        self,
        WB_1: memoryview,
        RB_1: memoryview,
        WB_2: memoryview,
        RB_2: memoryview,
    ) -> None:
        """Advance exchange simulation or yield execution thread based on stream read times.

        Parameters
        ----------
        WB_1 : memoryview
            Write pointer buffer for the signal stream ring buffer.
        RB_1 : memoryview
            Read pointer buffer for the signal stream ring buffer.
        WB_2 : memoryview
            Write pointer buffer for the user data stream ring buffer.
        RB_2 : memoryview
            Read pointer buffer for the user data stream ring buffer.
        """
        if self.trade_read_time[0] > self.exchange_sim.trade_read_time[0]:
            if (WB_1[0] != RB_1[0]) or (WB_2[0] != RB_2[0]):
                return
            self.exchange_sim.start(self.trade_read_time[0])
        else:
            time.sleep(0.001)

    @override
    def pre_execute_signal_action(self, time_get_signal: int) -> None:
        """Advance exchange simulation up to the signal timestamp and drain user data buffers.

        Parameters
        ----------
        time_get_signal : int
            Target timestamp in microseconds up to which simulation must progress.
        """
        while self.exchange_sim.trade_read_time[0] != time_get_signal:
            self.exchange_sim.start(time_get_signal)
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
        """Submit an order with simulated exchange latency and lock corresponding balances.

        Parameters
        ----------
        timestamp : int
            Generation timestamp of the order request.
        order_param : int
            Bitfield flags specifying order side, type, and parameters.
        client_order_id : int
            Unique client-assigned identifier for the order.
        nPrice : int
            Normalized order price.
        nQty : int
            Normalized order quantity.
        """
        timestamp = timestamp + self.exchange_sim.latency[0]
        Base.send_order(
            self, timestamp, order_param, client_order_id, nPrice, nQty
        )
        self.exchange_sim.lock_balance(nPrice, nQty, order_param)

    @override
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None:
        """Process raw user data payloads, updating order history and triggering callbacks.

        Parameters
        ----------
        user_data_raw_buf : memoryview
            Memory view containing raw user data fields from the ring buffer.
        """
        timestamp: int = user_data_raw_buf[c.TP_timestamp]
        order_param: int = user_data_raw_buf[c.TP_order_param]
        order_id: int = user_data_raw_buf[c.TP_order_id]
        client_order_id: int = user_data_raw_buf[c.TP_client_order_id]
        nPrice: int = user_data_raw_buf[c.TP_nPrice]
        nQty: int = user_data_raw_buf[c.TP_nQty]
        nCommission: int = user_data_raw_buf[c.TP_nCommission]
        nMAE: int = user_data_raw_buf[c.TP_nMAE]
        nMFE: int = user_data_raw_buf[c.TP_nMFE]

        _ = self.account
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
            planned_tp=(
                _._long_tp_dev if (order_param & c.OF_LONG) else _._short_tp_dev
            ),
            planned_sl=(
                _._long_sl_dev if (order_param & c.OF_LONG) else _._short_sl_dev
            ),
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
        """Finalize simulation execution, drain remaining buffers, and log metrics."""
        _ = self.exchange_sim
        # - - -
        while _.trade_read_time[0] != self.trade_read_time[0]:
            _.start(self.trade_read_time[0])
            self._check_user_data_buf()

        _.final_action()
        self.manager.set_log(
            f"Balance: {_.nBalance[0] / _.scale_mult[0]} \n"
            + f"Locked Balance: {_.lockedNbalance[0] / _.scale_mult[0]} \n"
            + f"Unrealized PNL: {_.unrealizedNpnl[0] / _.scale_mult[0]} \n"
            + f"Long Unrealized PNL: {_.longUnrealizedNpnl[0] / _.scale_mult[0]} \n"
            + f"Short Unrealized PNL: {_.shortUnrealizedNpnl[0] / _.scale_mult[0]} \n"
            + f"Long Open Qty: {_.longNqty[0] / _.qty_mult[0]} \n"
            + f"Short Open Qty: {_.shortNqty[0] / _.qty_mult[0]} \n"
            + f"Count Orders in History: {_.ohWid[0]} \n"
            + f"Count Active Orders: {_.obRow[0]} \n"
            + f"Count Open Positions: {self.count_open_positions[0]}"
        )
