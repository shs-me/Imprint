import struct
import time
from dataclasses import dataclass
from typing import override

from imprint.core.footprint import SyncWithExecution
from imprint.core.pipeline.engine.base import Base


@dataclass(slots=True)
class SyncViaSpinLock(SyncWithExecution):
    @override
    def sync_with_execution(self) -> None:
        pass


@dataclass(slots=True)
class Backtest(Base):
    @override
    def alarm_clock(self) -> None:
        time.sleep(0)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        self.agg_trades[self.at_wid, :] = struct.unpack("@qqqq", raw_data)
        self.at_wid: int = (
            self.at_wid + 1 if (self.at_wid + 1) < self.at_max_row else 0
        )

    @override
    def post_update(self) -> None:
        pass

    @override
    def post_final_action(self) -> None:
        pass
