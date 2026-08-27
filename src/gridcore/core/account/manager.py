from datetime import datetime

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from .. import constant as c
from ..ipc import NodeManager
from .converter import to_nMargin, to_nPnl

EquityT, EquityO, EquityH, EquityL, EquityC = 0, 1, 2, 3, 4


class Manager:
    def __init__(self, manager: NodeManager) -> None:
        cfgCoin = manager.cfgCoin
        self.price_prec: int = cfgCoin.price_prec
        self.qty_prec: int = cfgCoin.qty_prec
        self.price_mult: int = cfgCoin.price_mult
        self.qty_mult: int = cfgCoin.qty_mult

        cfgAC = manager.cfgAccount
        self.scale_prec: int = cfgAC.scale_prec
        self.scale_mult: int = cfgAC.scale_mult
        self.latency: int = cfgAC.latency_ms
        self.leverage: int = cfgAC.leverage
        self.takerNcommission: int = cfgAC.taker_commission.int_
        self.makerNcommission: int = cfgAC.maker_commission.int_
        self.startNbalance: int = round(cfgAC.balance * self.scale_mult)

        cfgFP = manager.cfgFootprint
        self.timeframe: int = int(cfgFP.timeframe)
        start_dt: datetime = datetime.fromisoformat(
            manager.cfgSetup.backtest_start_date
        )
        end_dt: datetime = datetime.fromisoformat(manager.cfgSetup.backtest_end_date)
        total_days: int = max(1, (end_dt - start_dt).days + 1)
        self.bar_count: int = (total_days * 24 * 60 * 60 * 1000) // self.timeframe

        self.equity_history: NDArray[int64] = np.zeros(
            (self.bar_count, EquityC + 1), dtype=int64
        )

        self.base_timestamp: memoryview = memoryview(bytearray(8)).cast("q")

        self.nBalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.lockedNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.availableNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.dynamicNbalance: memoryview = memoryview(bytearray(8)).cast("q")
        self.longNqty: memoryview = memoryview(bytearray(8)).cast("q")
        self.longEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortNqty: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortEntryNprice: memoryview = memoryview(bytearray(8)).cast("q")

        self.unrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self.longUnrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self.shortUnrealizedNpnl: memoryview = memoryview(bytearray(8)).cast("q")
        self.long_mae: memoryview = memoryview(bytearray(8)).cast("q")
        self.long_mfe: memoryview = memoryview(bytearray(8)).cast("q")
        self.short_mae: memoryview = memoryview(bytearray(8)).cast("q")
        self.short_mfe: memoryview = memoryview(bytearray(8)).cast("q")

        self.nBalance[0] = self.startNbalance
        self.availableNbalance[0] = self.startNbalance
        self.dynamicNbalance[0] = self.startNbalance

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
    def final_action(self) -> None:
        """Flushes non-zero equity history bars to disk."""

        self.dump_equity_history()

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
