from multiprocessing.synchronize import Event

from ....utils.handlers import supervisor
from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.status_codes import StatusCodes as scs
from ...base.base_footprint_reader import FootprintReader
from ...base.base_logic import Logic, resolve_reader
from ...base.base_sync import Sync


class SyncTool(Sync):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager)

        self.execution_event: Event = execution_event

    def sync_with_execution(self) -> None:
        if self.execution_event.is_set() is False:
            self.execution_event.set()


class LogicAgent(Logic):
    def __init__(
        self, manager: AgentManager, reader: FootprintReader, logic_event: Event
    ) -> None:
        super().__init__(manager=manager, reader=reader)

        self.logic_event: Event = logic_event

    def alarm_clock(self) -> None:
        if (self.reader._spare_flag[0] == 0) and (self.parsing_complete[0] == 0):
            if self.logic_event.is_set() is False:
                self.logic_event.wait()

    def post_update(self) -> None:
        if self.logic_event.is_set():
            self.logic_event.clear()

    def check_lag(self) -> None:
        if self.reader._sync.lag_is_safe() is False:
            self.pass_lag += 1
            if self.pass_lag >= self.pass_lag_limit:
                self.set_proc_sc(scs.ANALYSIS_LAG_MORE_SAFE_LAG)

    def post_final_action(self) -> None:
        self.reader._sync.sync_with_execution()


@supervisor()
def run_logic(logic_event: Event, execution_event: Event, **kwargs) -> None:
    sync = SyncTool(kwargs["manager"], execution_event)
    reader = resolve_reader(kwargs["manager"], sync)
    agent = LogicAgent(kwargs["manager"], reader, logic_event)
    agent.run_logic_engine()
