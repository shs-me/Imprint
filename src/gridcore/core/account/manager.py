from dataclasses import dataclass, field
from datetime import datetime
from typing import final

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from .. import constant as c
from ..ipc import NodeManager
from .converter import to_nMargin, to_nPnl

EquityT, EquityO, EquityH, EquityL, EquityC = 0, 1, 2, 3, 4


@dataclass
class Manager:
    manager: NodeManager

    price_prec: int = field(init=False)
    qty_prec: int = field(init=False)
    price_mult: int = field(init=False)
    qty_mult: int = field(init=False)
    scale_prec: int = field(init=False)
    scale_mult: int = field(init=False)
    latency: int = field(init=False)
    leverage: int = field(init=False)
    takerNcommission: int = field(init=False)
    makerNcommission: int = field(init=False)
    startNbalance: int = field(init=False)
    timeframe: int = field(init=False)
    bar_count: int = field(init=False)
    equity_history: NDArray[int64] = field(init=False)
    base_timestamp: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    nBalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    lockedNbalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    availableNbalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    dynamicNbalance: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    longNqty: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    longEntryNprice: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    shortNqty: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    shortEntryNprice: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    unrealizedNpnl: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    longUnrealizedNpnl: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    shortUnrealizedNpnl: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    long_mae: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    long_mfe: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    short_mae: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    short_mfe: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    def __post_init__(self) -> None:
        cfgCoin = self.manager.cfgCoin
        self.price_prec = cfgCoin.price_prec
        self.qty_prec = cfgCoin.qty_prec
        self.price_mult = cfgCoin.price_mult
        self.qty_mult = cfgCoin.qty_mult

        cfgAC = self.manager.cfgAccount
        self.scale_prec = cfgAC.scale_prec
        self.scale_mult = cfgAC.scale_mult
        self.latency = cfgAC.latency_ms
        self.leverage = cfgAC.leverage
        self.takerNcommission = cfgAC.taker_commission.int_
        self.makerNcommission = cfgAC.maker_commission.int_
        self.startNbalance = round(cfgAC.balance * self.scale_mult)

        cfgFP = self.manager.cfgFootprint
        self.timeframe = int(cfgFP.timeframe)

        start_dt: datetime = datetime.fromisoformat(
            self.manager.cfgSetup.backtest_start_date
        )
        end_dt: datetime = datetime.fromisoformat(
            self.manager.cfgSetup.backtest_end_date
        )
        total_days: int = max(1, (end_dt - start_dt).days + 1)

        self.bar_count = (total_days * 24 * 60 * 60 * 1000) // self.timeframe

        self.equity_history = np.zeros((self.bar_count, EquityC + 1), dtype=int64)

        self.nBalance[0] = self.startNbalance
        self.availableNbalance[0] = self.startNbalance
        self.dynamicNbalance[0] = self.startNbalance

    @final
    def update_local_lockedNbalance(
        self, nPrice: int, nQty: int, order_param: int
    ) -> None:
        is_long = bool(order_param & c.OF_LONG)
        is_buy = bool(order_param & c.OF_BUY)
        if (is_buy and is_long) or (not is_long and not is_buy):
            if bool(order_param & c.OF_LIMIT):
                self.lockedNbalance[0] += to_nMargin(
                    nPrice,
                    nQty,
                    self.leverage,
                    self.price_mult,
                    self.qty_mult,
                    self.scale_mult,
                )

        self.post_update_lockedNbalance()

    def post_update_lockedNbalance(self) -> None:
        pass

    # Agent Methods
    @final
    def final_action(self) -> None:
        """Flushes non-zero equity history bars to disk."""

        self.dump_equity_history()

    @final
    def dump_equity_history(self) -> None:
        """Saves active equity history array to disk."""

        valid_mask = self.equity_history[:, 0] > 0
        np.save(c.EQUITY_HISTORY_DUMP_PATH, self.equity_history[valid_mask])


@njit(cache=True)
def update_unrealized_nPnl(
    trade_nPrice: int,
    unrealizedNpnl: memoryview,
    longUnrealizedNpnl: memoryview,
    shortUnrealizedNpnl: memoryview,
    longNqty: memoryview,
    shortNqty: memoryview,
    longEntryNprice: memoryview,
    shortEntryNprice: memoryview,
    price_mult: int,
    qty_mult: int,
    scale_mult: int,
    long_mae: memoryview,
    long_mfe: memoryview,
    short_mae: memoryview,
    short_mfe: memoryview,
) -> int:
    if longNqty[0] or shortNqty[0]:
        if longNqty[0]:
            longUnrealizedNpnl[0] = to_nPnl(
                trade_nPrice,
                longNqty[0],
                True,
                longEntryNprice[0],
                shortEntryNprice[0],
                price_mult,
                qty_mult,
                scale_mult,
            )
            if longUnrealizedNpnl[0] < long_mae[0]:
                long_mae[0] = longUnrealizedNpnl[0]
            if longUnrealizedNpnl[0] > long_mfe[0]:
                long_mfe[0] = longUnrealizedNpnl[0]
        else:
            longUnrealizedNpnl[0] = 0

        if shortNqty[0]:
            shortUnrealizedNpnl[0] = to_nPnl(
                trade_nPrice,
                shortNqty[0],
                False,
                longEntryNprice[0],
                shortEntryNprice[0],
                price_mult,
                qty_mult,
                scale_mult,
            )
            if shortUnrealizedNpnl[0] < short_mae[0]:
                short_mae[0] = shortUnrealizedNpnl[0]
            if shortUnrealizedNpnl[0] > short_mfe[0]:
                short_mfe[0] = shortUnrealizedNpnl[0]
        else:
            shortUnrealizedNpnl[0] = 0
    else:
        longUnrealizedNpnl[0], shortUnrealizedNpnl[0] = 0, 0

    unrealizedNpnl[0] = longUnrealizedNpnl[0] + shortUnrealizedNpnl[0]
    return unrealizedNpnl[0]


@njit(cache=True)
def update_equity_ohlc(
    trade_timestamp: int,
    current_equity: int,
    equity_history: NDArray[int64],
    base_timestamp: memoryview,
    timeframe: int,
) -> None:
    ce, eh = current_equity, equity_history
    # - - -
    if base_timestamp[0] == 0:
        base_timestamp[0] = trade_timestamp - (trade_timestamp % timeframe)

    bar: int = (trade_timestamp - base_timestamp[0]) // timeframe
    max_bars: int = equity_history.shape[0]

    if 0 <= bar < max_bars:
        if equity_history[bar, EquityT] == 0:
            bar_open_time: int = base_timestamp[0] + (bar * timeframe)
            eh[bar, :] = bar_open_time, ce, ce, ce, ce

            prev_bar: int = bar - 1
            prev_eq: int = ce
            while prev_bar >= 0:
                if equity_history[prev_bar, 0] == 0:
                    prev_bar -= 1
                else:
                    prev_eq = equity_history[prev_bar, EquityC]
                    prev_bar += 1
                    break

            while 0 <= prev_bar < bar:
                eh[prev_bar, EquityT] = base_timestamp[0] + (prev_bar * timeframe)
                eh[prev_bar, EquityO:] = prev_eq, prev_eq, prev_eq, prev_eq
                prev_bar += 1
        else:
            if current_equity > equity_history[bar, EquityH]:
                equity_history[bar, EquityH] = current_equity
            if current_equity < equity_history[bar, EquityL]:
                equity_history[bar, EquityL] = current_equity
            equity_history[bar, EquityC] = current_equity
