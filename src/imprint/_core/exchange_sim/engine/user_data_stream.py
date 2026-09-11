from abc import ABC
from dataclasses import dataclass, field
from typing import override

from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint._core.exchange_sim.engine.order_stream import Order


@dataclass(slots=True)
class UserData(Order, ABC):
    uds_data_buf: memoryview = field(init=False)
    uds_data_size: int = field(init=False)
    uds_data_header_buf: memoryview = field(init=False)
    uds_wid_buf: memoryview = field(init=False)
    uds_cell_amount: int = field(init=False)

    @override
    def __post_init__(self) -> None:
        Order.__post_init__(self)

        uds = self.manager.cfgUserDataStream.ring_buf
        self.uds_data_buf = uds.data_buf
        self.uds_data_size = uds.data_size
        self.uds_data_header_buf = uds.data_header_buf
        self.uds_wid_buf = uds.wid_buf
        self.uds_cell_amount = uds.cell_amount


@njit(cache=True)
def set_user_data(
    data: NDArray[int64],
    uds_data_buf: memoryview,
    uds_data_buf_size: int,
    uds_data_header_buf: memoryview,
    uds_wid_buf: memoryview,
    uds_cell_amount: int,
) -> None:
    cell: int = uds_wid_buf[0]
    start: int = cell * uds_data_buf_size

    lrd: int = len(data)
    uds_data_header_buf[cell] = lrd
    for i in range(lrd):
        uds_data_buf[start + i] = data[i]

    new_cell: int = cell + 1
    uds_wid_buf[0] = new_cell if (new_cell < uds_cell_amount) else 0
