from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from typing import final, override

import numpy as np
from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint.core import constant as c
from imprint.core.exchange.account.position import Position

EquityT, EquityO, EquityH, EquityL, EquityC = 0, 1, 2, 3, 4


@dataclass
class Manager(Position, ABC):
    latency: int = field(init=False)

    timeframe: int = field(init=False)
    bar_count: int = field(init=False)
    equity_history: NDArray[int64] = field(init=False)
    base_timestamp: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    @override
    def __post_init__(self) -> None:
        Position.__post_init__(self)

        cfgAC = self.manager.cfgAccount
        self.latency = cfgAC.latency_ms

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

        self.equity_history = np.zeros(
            (self.bar_count, EquityC + 1), dtype=int64
        )

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
                eh[prev_bar, EquityT] = base_timestamp[0] + (
                    prev_bar * timeframe
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
