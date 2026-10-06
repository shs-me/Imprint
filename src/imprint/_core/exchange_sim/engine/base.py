from __future__ import annotations

from dataclasses import dataclass, field
from typing import override

import numba as nb
from numba import types  # pyright: ignore[reportPrivateImportUsage]
from numba.experimental import (
    jitclass,  # pyright: ignore[reportUnknownVariableType, reportPrivateImportUsage]
)
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.exchange_sim.account.manager import update_equity_ohlc
from imprint._core.exchange_sim.account.position import JitPosition
from imprint._core.exchange_sim.engine.matching_engine import (
    JitMatchingEngine,
    MatchingEngine,
)
from imprint._core.exchange_sim.engine.user_data_stream import set_user_data
from imprint._core.ipc import NodeManager

EquityT, EquityO, EquityH, EquityL, EquityC = 0, 1, 2, 3, 4


@dataclass(slots=True)
class Base(MatchingEngine):
    """Base class for the exchange simulation engine coordinating market data and matching.

    Attributes
    ----------
    trade_read_time : memoryview
        Single-element memoryview containing the current read timestamp index.
    _engine : JitExchangeEngine
        Numba-accelerated exchange engine instance driving low-level matching and metrics.
    """

    trade_read_time: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    _engine: JitExchangeEngine = field(init=False)

    @override
    def post_init(self, manager: NodeManager) -> None:
        MatchingEngine.post_init(self, manager)

        if not hasattr(self, "_engine"):
            mds = self.manager.cfgMarketDataStream.ring_buf
            self._engine = JitExchangeEngine(
                matching_engine=self.matching_engine,
                position=self.position,
                availableNbalance=self.availableNbalance,
                dynamicNbalance=self.dynamicNbalance,
                trade_read_time=self.trade_read_time,
                base_timestamp=self.base_timestamp,
                mds_data_size=mds.data_size,
                mds_data_buf=mds.data_buf,
                mds_rid_buf=mds.rid_buf,
                mds_cell_amount=mds.cell_amount,
                uds_data_size=self.uds_data_size,
                uds_data_buf=self.uds_data_buf,
                uds_data_header_buf=self.uds_data_header_buf,
                uds_wid_buf=self.uds_wid_buf,
                uds_cell_amount=self.uds_cell_amount,
                makerNcommission=self.makerNcommission,
                takerNcommission=self.takerNcommission,
                timeframe=self.timeframe,
                equity_history=self.equity_history,
            )

    def final_action(self) -> None:
        """Dump equity history and save orders history to persistent storage."""
        self.dump_equity_history()
        self.save_orders_history()

    def start(self, timestamp: int) -> None:
        """Start simulation processing up to the specified target timestamp.

        Parameters
        ----------
        timestamp : int
            Target simulation timestamp in microseconds.
        """
        self._engine.start(timestamp)


spec = [  # pyright: ignore[reportUnknownVariableType]
    ("matching_engine", JitMatchingEngine.class_type.instance_type),  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
    ("position", JitPosition.class_type.instance_type),  # pyright: ignore[reportAttributeAccessIssue,reportUnknownMemberType]
    ("availableNbalance", types.MemoryView(nb.int64, 1, "C")),
    ("dynamicNbalance", types.MemoryView(nb.int64, 1, "C")),
    ("trade_read_time", types.MemoryView(nb.int64, 1, "C")),
    ("base_timestamp", types.MemoryView(nb.int64, 1, "C")),
    ("mds_data_size", nb.int64),
    ("mds_data_buf", types.MemoryView(nb.int64, 1, "C")),
    ("mds_rid_buf", types.MemoryView(nb.int64, 1, "C")),
    ("mds_cell_amount", nb.int64),
    ("uds_data_size", nb.int64),
    ("uds_data_buf", types.MemoryView(nb.int64, 1, "C")),
    ("uds_data_header_buf", types.MemoryView(nb.int64, 1, "C")),
    ("uds_wid_buf", types.MemoryView(nb.int64, 1, "C")),
    ("uds_cell_amount", nb.int64),
    ("makerNcommission", nb.int64),
    ("takerNcommission", nb.int64),
    ("timeframe", nb.int64),
    ("equity_history", types.Array(nb.int64, 2, "C")),
]


@jitclass(spec)  # pyright: ignore[reportCallIssue, reportUntypedClassDecorator]
class JitExchangeEngine:
    """Numba-accelerated exchange simulation engine processing market data feeds and order matching.

    Parameters
    ----------
    matching_engine : JitMatchingEngine
        JIT-compiled order book matching engine.
    position : JitPosition
        JIT-compiled account position tracker.
    availableNbalance : memoryview
        Single-element memoryview of integer available normalized balance.
    dynamicNbalance : memoryview
        Single-element memoryview of integer dynamic/total normalized balance.
    trade_read_time : memoryview
        Single-element memoryview storing the last processed trade timestamp.
    base_timestamp : memoryview
        Single-element memoryview containing the simulation epoch base timestamp.
    mds_data_size : int
        Size of each market data cell in the buffer.
    mds_data_buf : memoryview
        Ring buffer storage for market data.
    mds_rid_buf : memoryview
        Ring buffer read pointer and index control state.
    mds_cell_amount : int
        Total cell capacity of the market data ring buffer.
    uds_data_size : int
        Size of each user data record.
    uds_data_buf : memoryview
        User data storage buffer.
    uds_data_header_buf : memoryview
        User data stream header buffer.
    uds_wid_buf : memoryview
        User data write pointer buffer.
    uds_cell_amount : int
        Total cell capacity of the user data stream buffer.
    makerNcommission : int
        Scaled integer fee rate applied to maker orders.
    takerNcommission : int
        Scaled integer fee rate applied to taker orders.
    timeframe : int
        Candle timeframe duration in milliseconds.
    equity_history : ndarray of shape (N, 5)
        Historical equity OHLCV array structured with `[Timestamp, Open, High, Low, Close]`.

    Attributes
    ----------
    matching_engine : JitMatchingEngine
        JIT-compiled order book matching engine.
    position : JitPosition
        JIT-compiled account position tracker.
    availableNbalance : memoryview
        Single-element memoryview of integer available normalized balance.
    dynamicNbalance : memoryview
        Single-element memoryview of integer dynamic/total normalized balance.
    trade_read_time : memoryview
        Single-element memoryview storing the last processed trade timestamp.
    base_timestamp : memoryview
        Single-element memoryview containing the simulation epoch base timestamp.
    mds_data_size : int
        Size of each market data cell in the buffer.
    mds_data_buf : memoryview
        Ring buffer storage for market data.
    mds_rid_buf : memoryview
        Ring buffer read pointer and index control state.
    mds_cell_amount : int
        Total cell capacity of the market data ring buffer.
    uds_data_size : int
        Size of each user data record.
    uds_data_buf : memoryview
        User data storage buffer.
    uds_data_header_buf : memoryview
        User data stream header buffer.
    uds_wid_buf : memoryview
        User data write pointer buffer.
    uds_cell_amount : int
        Total cell capacity of the user data stream buffer.
    makerNcommission : int
        Scaled integer fee rate applied to maker orders.
    takerNcommission : int
        Scaled integer fee rate applied to taker orders.
    timeframe : int
        Candle timeframe duration in milliseconds.
    equity_history : ndarray of shape (N, 5)
        Historical equity OHLCV array structured with `[Timestamp, Open, High, Low, Close]`.
    """

    def __init__(
        self,
        matching_engine: JitMatchingEngine,
        position: JitPosition,
        availableNbalance: memoryview,
        dynamicNbalance: memoryview,
        trade_read_time: memoryview,
        base_timestamp: memoryview,
        mds_data_size: int,
        mds_data_buf: memoryview,
        mds_rid_buf: memoryview,
        mds_cell_amount: int,
        uds_data_size: int,
        uds_data_buf: memoryview,
        uds_data_header_buf: memoryview,
        uds_wid_buf: memoryview,
        uds_cell_amount: int,
        makerNcommission: int,
        takerNcommission: int,
        timeframe: int,
        equity_history: NDArray[int64],
    ) -> None:
        self.matching_engine: JitMatchingEngine = matching_engine
        self.position: JitPosition = position
        self.availableNbalance: memoryview = availableNbalance
        self.dynamicNbalance: memoryview = dynamicNbalance
        self.trade_read_time: memoryview = trade_read_time
        self.base_timestamp: memoryview = base_timestamp
        self.mds_data_size: int = mds_data_size
        self.mds_data_buf: memoryview = mds_data_buf
        self.mds_rid_buf: memoryview = mds_rid_buf
        self.mds_cell_amount: int = mds_cell_amount
        self.uds_data_size: int = uds_data_size
        self.uds_data_buf: memoryview = uds_data_buf
        self.uds_data_header_buf: memoryview = uds_data_header_buf
        self.uds_wid_buf: memoryview = uds_wid_buf
        self.uds_cell_amount: int = uds_cell_amount
        self.makerNcommission: int = makerNcommission
        self.takerNcommission: int = takerNcommission
        self.timeframe: int = timeframe
        self.equity_history: NDArray[int64] = equity_history

    def start(self, timestamp: int) -> None:
        """Advance simulation state by consuming market data ring buffer ticks up to the target timestamp.

        Parameters
        ----------
        timestamp : int
            Target simulation timestamp in microseconds to advance up to.
        """
        ma = self.matching_engine
        # - - -
        while self.trade_read_time[0] != timestamp:
            cell: int = self.mds_rid_buf[1]
            start: int = cell * self.mds_data_size

            self.trade_read_time[0] = trade_timestamp = self.mds_data_buf[
                start + 2
            ]
            trade_nPrice: int = self.mds_data_buf[start]

            new_cell: int = cell + 1
            self.mds_rid_buf[1] = (
                new_cell if new_cell < self.mds_cell_amount else 0
            )

            self._processing_metrics(
                nPrice=trade_nPrice, timestamp=trade_timestamp
            )

            if ma.obRow[0] == 0:
                continue

            executed: bool = ma.matching(
                trade_timestamp=trade_timestamp, trade_nPrice=trade_nPrice
            )
            if executed:
                self._processing_executed_orders()

            self._processing_metrics(
                nPrice=trade_nPrice, timestamp=trade_timestamp
            )

            if executed:
                break

    def _processing_metrics(self, nPrice: int, timestamp: int) -> None:
        """Update unrealized PnL, account balances, MAE/MFE metrics, and equity OHLC bars.

        Parameters
        ----------
        nPrice : int
            Normalized trade price used for marking positions to market.
        timestamp : int
            Current trade timestamp in microseconds.
        """
        pos = self.position
        # - - -
        uNpnl = pos.update_unrealized_nPnl(nPrice=nPrice)
        self.dynamicNbalance[0] = pos.nBalance[0] + uNpnl
        self.availableNbalance[0] = (
            self.dynamicNbalance[0] - pos.lockedNbalance[0]
        )
        pos.update_mae_and_mfe()
        update_equity_ohlc(
            trade_timestamp=timestamp,
            current_equity=self.dynamicNbalance[0],
            equity_history=self.equity_history,
            base_timestamp=self.base_timestamp,
            timeframe=self.timeframe,
        )

    def _processing_executed_orders(self) -> None:
        """Process filled, canceled, or newly triggered orders from the matching engine execution buffer."""
        pos, ma = self.position, self.matching_engine
        # - - -
        for eo_row in range(ma.eoRow[0]):
            ma.eoRow[0] -= 1

            order_param = ma.executed_orders[eo_row, c.TP_order_param]
            nPrice = ma.executed_orders[eo_row, c.TP_nPrice]
            nQty = ma.executed_orders[eo_row, c.TP_nQty]

            is_buy: bool = bool(order_param & c.OF_BUY)
            is_long: bool = bool(order_param & c.OF_LONG)
            is_maker: bool = bool(order_param & c.OF_LIMIT)

            is_open: bool = (is_buy and is_long) or (not is_buy and not is_long)

            if bool(order_param & c.OF_FILLED):
                rate: int = (
                    self.makerNcommission if is_maker else self.takerNcommission
                )
                commission: float = (
                    ((nPrice / pos.price_mult) * (nQty / pos.qty_mult))
                    * rate
                    / 10_000
                )
                nCommission: int = round(commission * pos.scale_mult)
                ma.executed_orders[eo_row, c.TP_nCommission] = nCommission

                if not is_open:
                    if is_long:
                        ma.executed_orders[eo_row, c.TP_nMAE] = pos.long_mae[0]
                        ma.executed_orders[eo_row, c.TP_nMFE] = pos.long_mfe[0]
                    else:
                        ma.executed_orders[eo_row, c.TP_nMAE] = pos.short_mae[0]
                        ma.executed_orders[eo_row, c.TP_nMFE] = pos.short_mfe[0]

                self.position.update_position(
                    nPrice=nPrice,
                    nQty=nQty,
                    is_long=is_long,
                    is_open=is_open,
                    is_maker=is_maker,
                    nCommission=nCommission,
                )

            elif bool(order_param & c.OF_NEW) and (not is_maker):
                continue

            elif bool(order_param & c.OF_CANCELED) and is_open:
                pos.lockedNbalance[0] -= pos.to_nMargin(nPrice, nQty)

            set_user_data(
                data=ma.executed_orders[eo_row, :],
                uds_data_buf=self.uds_data_buf,
                uds_data_buf_size=self.uds_data_size,
                uds_data_header_buf=self.uds_data_header_buf,
                uds_wid_buf=self.uds_wid_buf,
                uds_cell_amount=self.uds_cell_amount,
            )
