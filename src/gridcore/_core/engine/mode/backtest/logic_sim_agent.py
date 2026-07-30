"""Simulated logic process and signal synchronization worker."""

import time

from ....utils.handlers import supervisor
from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_footprint_reader import FootprintReader
from ...base.base_logic import Logic, resolve_reader
from ...base.base_sync import Sync


class SyncTool(Sync):
    """Simulation signal synchronization tool inheriting from Sync."""

    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager)


class LogicAgent(Logic):
    """Logic engine agent evaluating strategy pattern callbacks in backtest mode."""

    def __init__(self, manager: AgentManager, reader: FootprintReader) -> None:
        super().__init__(manager=manager, reader=reader)

    def alarm_clock(self) -> None:
        """Idle wait loop checking shared memory spare flag updates."""

        while (self.reader._spare_flag[0] == 0) and (self.parsing_complete[0] == 0):
            time.sleep(0)

    def check_lag(self) -> None:
        return super().check_lag()

    def post_update(self) -> None:
        pass

    def post_final_action(self) -> None:
        """Logs generated signal count upon strategy completion."""

        self.manager.set_text(f"Count Signals: {self.reader._sync._count_send_signal}")


@supervisor()
def run_logic_sim(**kwargs) -> None:
    """Supervisor-wrapped entry point for simulated Logic process."""

    sync = SyncTool(kwargs["manager"])
    reader = resolve_reader(kwargs["manager"], sync)
    agent = LogicAgent(kwargs["manager"], reader)
    agent.run_logic_engine()
