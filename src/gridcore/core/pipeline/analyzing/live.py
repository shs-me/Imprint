from multiprocessing.synchronize import Event

from ...footprint import BaseFootprintReader, Sync
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from .base import Base


class SyncViaEvent(Sync):
    def __init__(self, manager: NodeManager, execution_event: Event) -> None:
        super().__init__(manager)

        self.execution_event: Event = execution_event

    def sync_with_execution(self) -> None:
        if self.execution_event.is_set() is False:
            self.execution_event.set()


class Live(Base):
    def __init__(
        self, manager: NodeManager, reader: BaseFootprintReader, logic_event: Event
    ) -> None:
        super().__init__(manager=manager, reader=reader)

        self.logic_event: Event = logic_event

    def alarm_clock(self) -> None:
        if (self.reader._spare_flags[0] == 0) and (self.parsing_complete[0] == 0):
            if self.logic_event.is_set() is False:
                self.logic_event.wait()

    def post_update(self) -> None:
        if self.reader._spare_flags[1] == 1:
            return

        if self.logic_event.is_set():
            self.logic_event.clear()

    def check_lag(self) -> None:
        if self.reader._sync.lag_is_safe() is False:
            self.pass_lag += 1
            if self.pass_lag >= self.pass_lag_limit:
                self.set_proc_sc(scs.ANALYSIS_LAG_MORE_SAFE_LAG, wait_main_task=False)

    def post_final_action(self) -> None:
        self.reader._sync.sync_with_execution()
        self.manager.set_text(f"Count Signals: {self.reader._sync._count_send_signal}")
