import time

from ...footprint import BaseFootprintReader, Sync
from ...ipc import NodeManager
from .base import Base


class SyncViaSpinLock(Sync):
    def __init__(self, manager: NodeManager) -> None:
        super().__init__(manager)

    def sync_with_execution(self) -> None:
        pass


class Backtest(Base):
    def __init__(self, manager: NodeManager, reader: BaseFootprintReader) -> None:
        super().__init__(manager=manager, reader=reader)

    def alarm_clock(self) -> None:
        time.sleep(0)

    def check_lag(self) -> None:
        pass

    def post_update(self) -> None:
        pass

    def post_final_action(self) -> None:
        self.manager.set_text(f"Count Signals: {self.reader._sync._count_send_signal}")
