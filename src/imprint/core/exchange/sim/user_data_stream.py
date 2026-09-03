from abc import ABC
from dataclasses import dataclass, field
from typing import override

import numpy as np
from numba import njit
from numpy import uint8
from numpy.typing import NDArray

from imprint.core.exchange.sim.order_stream import Order


@dataclass(slots=True)
class UserData(Order, ABC):
    gus_cell_amount: int = field(init=False)
    __gus_data: memoryview = field(init=False)
    gus_data_size: int = field(init=False)
    gus_data_header: memoryview = field(init=False)
    gus_wid: memoryview = field(init=False)
    __gus_rid: memoryview = field(init=False)

    gus_data_buf: NDArray[uint8] = field(init=False)

    @override
    def __post_init__(self) -> None:
        Order.__post_init__(self)

        cfgGUS = self.manager.cfgGetUserStream
        self.gus_cell_amount = cfgGUS.cell_amount
        self.__gus_data = cfgGUS.data.view
        self.gus_data_size = cfgGUS.data_size
        self.gus_data_header = cfgGUS.data_header.view
        self.gus_wid = cfgGUS.writer_id.view.cast("q")
        self.__gus_rid = cfgGUS.reader_id.view.cast("q")

        self.gus_data_buf = np.frombuffer(self.__gus_data, uint8)
        self.gus_data_buf.fill(0)


@njit(cache=True)
def set_user_data(
    data: NDArray[uint8],
    gus_data_buf: NDArray[uint8],
    gus_data_buf_size: int,
    gus_data_header: memoryview,
    gus_wid: memoryview,
    gus_cell_amount: int,
) -> None:
    cell: int = gus_wid[0]
    start: int = cell * gus_data_buf_size
    gus_data_header[cell] = len(data)
    gus_data_buf[start : start + len(data)] = data
    new_cell: int = cell + 1
    gus_wid[0] = new_cell if (new_cell < gus_cell_amount) else 0
