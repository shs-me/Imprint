from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from core.engine.agents_utils.logic.footprint_reader import FootprintReader
from core.utils.monitoring.agent_manager import AgentManager


class BaseFootprintReader(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)

    def _init_find_patterns_metadata(self) -> None | NDArray:
        return np.arange(10).reshape(5, 2)
