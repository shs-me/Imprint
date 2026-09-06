import time
from dataclasses import dataclass, field
from typing import override

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from imprint.core.pipeline.utils.base_data_prepare import BaseDataPrepare


@dataclass(slots=True)
class TickStream(BaseDataPrepare):
    price_mult: int

    dfm: NDArray[int64] = field(init=False)
    dfmWid: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    dfmRid: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    max_row: int = field(init=False)
    safe_lag: int = field(init=False)

    @override
    def __post_init__(self) -> None:
        BaseDataPrepare.__post_init__(self)

        self.dfm = np.ndarray((100_000, 2), dtype=int64)
        self.max_row = self.dfm.shape[0]
        self.safe_lag = round(self.max_row * 0.9)

    @override
    def alarm_clock(self) -> None:
        while (
            (self.dfmWid[0] - self.dfmRid[0] + self.max_row) % self.max_row
        ) > self.safe_lag:
            time.sleep(0)

    @override
    def prepare_data(self, line: NDArray[int64]) -> None:
        self.dfm[self.dfmWid[0], :] = line[0], line[2]
        new_row: int = self.dfmWid[0] + 1
        self.dfmWid[0] = new_row if (new_row < self.max_row) else 0

    @override
    def post_prepare(self) -> None:
        pass
