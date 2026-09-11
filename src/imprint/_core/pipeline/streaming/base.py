from abc import ABC
from dataclasses import dataclass, field
from typing import final

from imprint._core.ipc import NodeManager
from imprint._core.settings import StatusCodes as scs


@dataclass(slots=True)
class Base(ABC):
    manager: NodeManager

    symbol: str = field(init=False)

    ds_safe_lag: int = field(init=False)
    ds_cell_amount: int = field(init=False)
    ds_data_size: int = field(init=False)
    ds_data_header_size: int = field(init=False)
    ds_data: memoryview = field(init=False)
    ds_data_header: memoryview = field(init=False)
    ds_wid: memoryview = field(init=False)
    ds_rid: memoryview = field(init=False)

    gus_safe_lag: int = field(init=False)
    gus_cell_amount: int = field(init=False)
    gus_data_size: int = field(init=False)
    gus_data_header_size: int = field(init=False)
    gus_data: memoryview = field(init=False)
    gus_data_header: memoryview = field(init=False)
    gus_wid: memoryview = field(init=False)
    gus_rid: memoryview = field(init=False)

    sus_safe_lag: int = field(init=False)
    sus_cell_amount: int = field(init=False)
    sus_data_size: int = field(init=False)
    sus_data_header_size: int = field(init=False)
    sus_data: memoryview = field(init=False)
    sus_data_header: memoryview = field(init=False)
    sus_rid: memoryview = field(init=False)
    sus_wid: memoryview = field(init=False)

    def __post_init__(self) -> None:
        self.symbol = self.manager.cfgCoin.symbol

        cfgDS = self.manager.cfgDataStream
        self.ds_safe_lag = cfgDS.ring_buf.safe_lag
        self.ds_cell_amount = cfgDS.ring_buf.cell_amount
        self.ds_data_size = cfgDS.ring_buf.data_size
        self.ds_data_header_size = cfgDS.ring_buf.data_header_size
        self.ds_data = cfgDS.ring_buf.data.view
        self.ds_data_header = cfgDS.ring_buf.data_header.view
        self.ds_wid = cfgDS.ring_buf.writer_id.view.cast("q")
        self.ds_rid = cfgDS.ring_buf.reader_id.view.cast("q")

        cfgGUS = self.manager.cfgGetUserStream
        self.gus_safe_lag = cfgGUS.ring_buf.safe_lag
        self.gus_cell_amount = cfgGUS.ring_buf.cell_amount
        self.gus_data_size = cfgGUS.ring_buf.data_size
        self.gus_data_header_size = cfgGUS.ring_buf.data_header_size
        self.gus_data = cfgGUS.ring_buf.data.view
        self.gus_data_header = cfgGUS.ring_buf.data_header.view
        self.gus_wid = cfgGUS.ring_buf.writer_id.view.cast("q")
        self.gus_rid = cfgGUS.ring_buf.reader_id.view.cast("q")

        cfgSUS = self.manager.cfgSetUserStream
        self.sus_safe_lag = cfgSUS.ring_buf.safe_lag
        self.sus_cell_amount = cfgSUS.ring_buf.cell_amount
        self.sus_data_size = cfgSUS.ring_buf.data_size
        self.sus_data_header_size = cfgSUS.ring_buf.data_header_size
        self.sus_data = cfgSUS.ring_buf.data.view
        self.sus_data_header = cfgSUS.ring_buf.data_header.view
        self.sus_wid = cfgSUS.ring_buf.writer_id.view.cast("q")
        self.sus_rid = cfgSUS.ring_buf.reader_id.view.cast("q")

    @final
    def lag_not_is_safe(
        self, wid: int, rid: int, cell_amount: int, safe_lag: int
    ) -> bool:
        return ((wid - rid + cell_amount) % cell_amount) > safe_lag

    @final
    def set_raw_data(
        self,
        raw_data: bytes | memoryview,
        writer_id: memoryview,
        data: memoryview,
        data_header: memoryview,
        data_size: int,
        cell_amount: int,
    ) -> bool:
        if (lrd := len(raw_data)) < data_size:
            cell: int = writer_id[0]
            data_header[cell] = lrd
            start: int = cell * data_size
            data[start : start + lrd] = raw_data
            new_cell = cell + 1
            writer_id[0] = new_cell if new_cell < cell_amount else 0
            return True
        else:
            self.manager.set_proc_sc(code=scs.BIG_RAW_DATA, wait_main_task=True)
            return False

    @final
    def final_actions(self) -> None:
        self.manager.set_log(" ")
