import time

from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ...base.base_footprint_reader import FootprintReader
from ...base.base_logic import Logic, resolve_reader
from ...base.base_sync import Sync


class SyncTool(Sync):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager)


class LogicAgent(Logic):
    def __init__(self, manager: AgentManager, reader: FootprintReader) -> None:
        super().__init__(manager=manager, reader=reader)

    def alarm_clock(self) -> None:
        while (self.reader.spare_flag[0] == 0) and (self.parsing_complete[0] == 0):
            time.sleep(0)

    def check_lag(self) -> None:
        return super().check_lag()

    def post_update(self) -> None:
        pass

    def post_final_action(self) -> None:
        self.manager.set_text(f"Count Signals: {self.reader.temp}")  # type: ignore


@manager_office()
def run_logic_sim(**kwargs) -> None:
    sync = SyncTool(kwargs["manager"])
    reader = resolve_reader(kwargs["manager"], sync)
    agent = LogicAgent(kwargs["manager"], reader)
    agent.run_logic_engine()
