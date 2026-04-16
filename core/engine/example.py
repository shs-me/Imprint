from multiprocessing.synchronize import Event

from .. import AgentManager
from . import FootprintReader


class BaseFootprintReader(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)

    def check_pattern(self):
        if self.P_shape():
            print(self.con.get_Bar_id(), "P-shape: True")
        if self.b_shape():
            print(self.con.get_Bar_id(), "b-shape: True")
