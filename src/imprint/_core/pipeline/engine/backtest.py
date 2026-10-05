import time
from dataclasses import dataclass
from typing import override

from imprint._core.footprint import SyncWithExecution
from imprint._core.pipeline.engine.base import Base


@dataclass(slots=True)
class SyncViaSpinLock(SyncWithExecution):
    """Synchronization mechanism via a spin lock for backtesting execution."""

    @override
    def sync_with_execution(self) -> None:
        """Synchronize strategy state with execution without blocking."""


@dataclass(slots=True)
class Backtest(Base):
    """Backtesting execution engine processing historical market data ticks.

    Parameters
    ----------
    manager : NodeManager
        Inter-process communication and configuration manager for the engine node.
    algorithm : StrategyEngine
        Active strategy container holding the footprint engine and synchronization state.
    """

    @override
    def alarm_clock(self) -> None:
        """Yield execution briefly via a short sleep when input buffers are empty."""
        time.sleep(0.001)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        """Copy raw trade data into the aggregated trades buffer and advance the write index.

        Parameters
        ----------
        raw_data : memoryview
            Raw binary trade payload from the data stream ring buffer.
        """
        self.agg_trades[self.at_wid, :] = raw_data[:]
        self.at_wid: int = (
            self.at_wid + 1 if (self.at_wid + 1) < self.at_max_row else 0
        )

    @override
    def post_update(self) -> None:
        """Perform post-update actions during backtesting."""

    @override
    def post_final_action(self) -> None:
        """Perform post-completion actions during backtesting."""
