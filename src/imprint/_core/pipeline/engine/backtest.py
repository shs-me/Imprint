import time
from dataclasses import dataclass
from typing import override

from imprint._core.footprint import SyncWithExecution
from imprint._core.pipeline.engine.base import Base


@dataclass(slots=True)
class SyncViaSpinLock(SyncWithExecution):
    @override
    def sync_with_execution(self) -> None:
        pass


@dataclass(slots=True)
class Backtest(Base):
    @override
    def alarm_clock(self) -> None:
        time.sleep(0.001)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        trade = raw_data.cast("q")
        self.agg_trades[self.at_wid, :] = trade[0], trade[1], trade[2], trade[3]
        self.at_wid: int = (
            self.at_wid + 1 if (self.at_wid + 1) < self.at_max_row else 0
        )

    @override
    def post_update(self) -> None:
        pass

    @override
    def post_final_action(self) -> None:
        pass
