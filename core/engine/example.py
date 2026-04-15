from .. import AgentManager
from . import FootprintReader


class BaseFootprintReader(FootprintReader):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager)

    def check_pattern(self):
        pass
