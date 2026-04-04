import numpy as np
from numpy.typing import NDArray

from core import GridReader, MonitorObj


class FootprintReader(GridReader):
    def __init__(self, mo: MonitorObj) -> None:
        super().__init__(mo)
        print(FootprintReader.__name__)

    def check_patterns(
        self, idy: int, idx: int, footprint: NDArray[np.float64]
    ) -> None:
        # LocalLinks
        to_idy, to_idx = self.convert.to_idy, self.convert.to_idx  # noqa: F841
        to_price, to_timestamp = self.convert.to_price, self.convert.to_timestamp
        round_to_tick = self.convert.round_to_tick
        # - - -
        price, timestamp = to_price(idy), to_timestamp(idx)  # noqa
        _price, _qty = round_to_tick(price), footprint[idy, idx]
        print(_price, _qty, flush=True)
