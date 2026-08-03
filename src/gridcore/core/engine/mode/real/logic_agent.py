"""Live strategy logic evaluation process and event synchronization worker."""

from multiprocessing.synchronize import Event

from ....settings import LogicProc
from ....settings import StatusCodes as scs
from ....utils.handlers import supervisor
from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_footprint_reader import FootprintReader
from ...base.base_logic import Logic, resolve_reader
from ...base.base_sync import Sync


class SyncTool(Sync):
    """Live signal synchronization tool notifying Execution process via event."""

    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager)

        self.execution_event: Event = execution_event

    def sync_with_execution(self) -> None:
        """Sets execution_event to awaken waiting Execution agent."""

        if self.execution_event.is_set() is False:
            self.execution_event.set()


class LogicAgent(Logic):
    """Live strategy evaluation process managed via inter-process events."""

    def __init__(
        self, manager: AgentManager, reader: FootprintReader, logic_event: Event
    ) -> None:
        super().__init__(manager=manager, reader=reader)

        self.logic_event: Event = logic_event

    def alarm_clock(self) -> None:
        """Blocks process on logic_event until Footprint update occurs."""

        if (self.reader._spare_flag[0] == 0) and (self.parsing_complete[0] == 0):
            if self.logic_event.is_set() is False:
                self.logic_event.wait()

    def post_update(self) -> None:
        """Clears logic_event after strategy evaluation cycle completes."""

        if self.logic_event.is_set():
            self.logic_event.clear()

    def check_lag(self) -> None:
        """Monitors system processing latency against safe thresholds and flags excessive lag."""

        if self.reader._sync.lag_is_safe() is False:
            self.pass_lag += 1
            if self.pass_lag >= self.pass_lag_limit:
                self.set_proc_sc(scs.ANALYSIS_LAG_MORE_SAFE_LAG)

    def post_final_action(self) -> None:
        self.reader._sync.sync_with_execution()


@supervisor()
def run_logic(
    logic_event: Event, execution_event: Event, proc: LogicProc = LogicProc(), **kwargs
) -> None:
    """Supervisor-wrapped entry point for live Logic process."""

    sync = SyncTool(kwargs["manager"], execution_event)
    reader = resolve_reader(kwargs["manager"], sync)
    agent = LogicAgent(kwargs["manager"], reader, logic_event)
    agent.run_logic_engine()
