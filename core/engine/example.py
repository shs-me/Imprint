from multiprocessing.synchronize import Event

from .. import AgentManager
from . import FootprintReader


class BaseFootprintReader(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)

    def check_pattern(self):
        if self.P_shape(bullish=False):
            print(self.last_idx - 2, "p-shape: True")
