from multiprocessing.synchronize import Event

from core.engine.analytical_tools.footprint.footprint_reader import FootprintReader
from core.utils.monitoring.agent_manager import AgentManager


class BaseFootprintReader(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)

    def check_pattern(self):
        pass
