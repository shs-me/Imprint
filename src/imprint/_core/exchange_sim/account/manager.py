from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import final, override

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint._core import constant as c
from imprint._core.exchange_sim.account.position import Position

EquityT, EquityO, EquityH, EquityL, EquityC = 0, 1, 2, 3, 4


@dataclass(slots=True)
class Manager(Position, ABC):
    """Manages trading account state, position metrics, and historical equity tracking.

    Attributes
    ----------
    latency : int
        Order routing and execution latency in milliseconds.
    timeframe : int
        Bar duration in milliseconds.
    bar_count : int
        Total number of OHLCV bars allocated across the backtest duration.
    equity_history : ndarray of shape (bar_count, 5)
        Time-series array storing historical equity OHLC records where columns
        represent timestamp (EquityT), open (EquityO), high (EquityH),
        low (EquityL), and close (EquityC).
    base_timestamp : memoryview
        Single-element 64-bit signed integer memoryview caching the anchor timestamp
        of the initial trading bar in milliseconds epoch time.
    """

    latency: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    timeframe: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    bar_count: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    equity_history: NDArray[int64] = field(
        default_factory=lambda: np.zeros((0, 0), dtype=int64), init=False
    )
    base_timestamp: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    @override
    def init(self) -> None:
        Position.init(self)

        cfgAC = self.manager.cfgAccount
        self.latency[0] = cfgAC.latency_ms

        cfgFP = self.manager.cfgFootprint
        self.timeframe[0] = int(cfgFP.timeframe)

        cfgSetup = self.manager.cfgSetup
        start_dt: datetime = datetime.fromisoformat(
            cfgSetup.backtest_start_date
        )
        end_dt: datetime = datetime.fromisoformat(cfgSetup.backtest_end_date)
        total_days: int = max(1, (end_dt - start_dt).days + 1)

        self.bar_count[0] = (
            total_days * 24 * 60 * 60 * 1000
        ) // self.timeframe[0]

        if self.bar_count[0] != self.equity_history.shape[0]:
            self.equity_history = np.zeros(
                (self.bar_count[0], EquityC + 1), dtype=int64
            )
        else:
            self.equity_history.fill(0)

    @override
    def reset(self) -> None:
        Position.reset(self)

        self.base_timestamp[0] = 0

    @final
    def dump_equity_history(self) -> None:
        """Serialize and persist the accumulated equity history array to disk."""
        np.save(c.EQUITY_HISTORY_DATA_PATH, self.equity_history)


@njit(cache=True)
def update_equity_ohlc(
    trade_timestamp: int,
    current_equity: int,
    equity_history: NDArray[int64],
    base_timestamp: memoryview,
    timeframe: memoryview,
) -> None:
    """Update historical equity OHLC bars given a new trade timestamp and equity value.

    Parameters
    ----------
    trade_timestamp : int
        Execution timestamp of the current trade in milliseconds.
    current_equity : int
        Account equity value at the time of the trade.
    equity_history : ndarray of shape (N, 5)
        Preallocated history buffer modified in-place where columns store
        timestamp, open, high, low, and close values respectively.
    base_timestamp : memoryview
        Mutable single-element 64-bit integer buffer storing the anchor epoch timestamp
        for the first bar. Initialized to zero on first write.
    timeframe : int
        Duration of each individual OHLC bar in milliseconds. Must be strictly positive.

    Notes
    -----
    Performs in-place updates on ``equity_history`` and handles gap-filling for unpopulated
    intermediate bars by carrying forward the previous close value.
    """
    ce, eh = current_equity, equity_history
    # - - -
    if base_timestamp[0] == 0:
        base_timestamp[0] = trade_timestamp - (trade_timestamp % timeframe[0])

    bar: int = (trade_timestamp - base_timestamp[0]) // timeframe[0]
    max_bars: int = equity_history.shape[0]

    if 0 <= bar < max_bars:
        if equity_history[bar, EquityT] == 0:
            bar_open_time: int = base_timestamp[0] + (bar * timeframe[0])
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
                eh[prev_bar, EquityT] = base_timestamp[0] + (
                    prev_bar * timeframe[0]
                )
                eh[prev_bar, EquityO:] = prev_eq, prev_eq, prev_eq, prev_eq
                prev_bar += 1
        else:
            equity_history[bar, EquityH] = max(
                equity_history[bar, EquityH], current_equity
            )
            equity_history[bar, EquityL] = min(
                equity_history[bar, EquityL], current_equity
            )
            equity_history[bar, EquityC] = current_equity
