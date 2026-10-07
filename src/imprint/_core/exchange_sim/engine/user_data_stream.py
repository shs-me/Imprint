from abc import ABC
from dataclasses import dataclass, field
from typing import override

from numba import njit
from numpy import int64
from numpy.typing import NDArray

from imprint._core.exchange_sim.engine.order_stream import Order


@dataclass(slots=True)
class UserData(Order, ABC):
    """Represents a user data stream order handler managing ring buffer allocations.

    Attributes
    ----------
    uds_data_buf : memoryview
        Shared memory buffer storing serialized user data items.
    uds_data_size : int
        Capacity of each slot in the user data ring buffer in bytes.
    uds_data_header_buf : memoryview
        Header buffer tracking payload lengths per cell slot.
    uds_wid_buf : memoryview
        Write index buffer pointing to the current active cell slot.
    uds_cell_amount : int
        Total number of cells allocated in the ring buffer.
    """

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
    """Write user data array into the active ring buffer cell and advance the write index.

    Parameters
    ----------
    data : ndarray of shape (N,), dtype=int64
        Source integer payload to write into the user data stream buffer.
    uds_data_buf : memoryview
        Shared memory buffer storing serialized user data items.
    uds_data_buf_size : int
        Maximum element capacity per buffer cell slot.
    uds_data_header_buf : memoryview
        Header buffer tracking payload lengths per cell slot, updated with ``len(data)``.
    uds_wid_buf : memoryview
        Write index buffer containing the current target cell index at position ``0``.
    uds_cell_amount : int
        Total number of cells in the ring buffer. Used to wrap around the write index.
    """
    cell: int = uds_wid_buf[0]
    start: int = cell * uds_data_buf_size

    lrd: int = len(data)
    uds_data_header_buf[cell] = lrd
    for i in range(lrd):
        uds_data_buf[start + i] = data[i]

    new_cell: int = cell + 1
    uds_wid_buf[0] = new_cell if (new_cell < uds_cell_amount) else 0
