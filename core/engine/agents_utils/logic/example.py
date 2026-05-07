from multiprocessing.synchronize import Event

from core.engine.agents_utils.logic.footprint_reader import FootprintReader
from core.utils.monitoring.agent_manager import AgentManager


class BaseFootprintReader(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)
        self.algorithm_metadata.resize((4, 4))
        self.row = 0
