from multiprocessing.synchronize import Event

from numpy import int64

from core.engine.agents_utils.logic.footprint_reader import FootprintReader
from core.utils.monitoring.agent_manager import AgentManager


class BaseFootprintReader(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)
        self.algorithm_metadata.resize((4, 4))
        self.row = 0

    def _update_clusters(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None:
        super()._update_clusters(idYmin, idYmax, idXmin, idXmax)
        pass

    def _update_closed_bar_and_fp(self) -> None:
        super()._update_closed_bar_and_fp()
        pass

    def _update_bar(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        super()._update_bar(idYmin, idYmax, idxBid, idxAsk)
        pass
