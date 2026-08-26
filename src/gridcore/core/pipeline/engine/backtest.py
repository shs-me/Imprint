import struct
import time
from typing import override

from ...footprint.engine import FootprintEngine, SyncWithExecution
from ...ipc import NodeManager
from .base import Base


class SyncViaSpinLock(SyncWithExecution):
    def __init__(self, manager: NodeManager) -> None:
        super().__init__(manager)

    @override
    def sync_with_execution(self) -> None:
        pass


class Backtest(Base):
    def __init__(self, manager: NodeManager, engine: FootprintEngine) -> None:
        super().__init__(manager, engine)

    @override
    def alarm_clock(self) -> None:
        time.sleep(0)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        data: tuple[int, int, int, int] = struct.unpack("@qqqq", raw_data)
        self.nPrice[0], self.nQty[0], self.timestamp[0], self.is_sell[0] = data

    @override
    def post_update(self) -> None:
        return super().post_update()

    @override
    def post_final_action(self) -> None:
        pass
