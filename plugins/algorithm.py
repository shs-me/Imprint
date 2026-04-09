import numpy as np
from numpy.typing import NDArray

from core import AgentManager, FootprintReader


class IntraDay(FootprintReader):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager)

    def check_patterns(self, idy: int, idx: int, footprint: NDArray[np.int64]) -> None:
        convert = self.convert
        get_nPice = convert.get_nPrice
        to_price, to_qty = convert.to_price, convert.to_qty
        # - - -
        price, qty = to_price(get_nPice(idy)), to_qty(footprint[idy, idx])
        print(price, qty, flush=True)
