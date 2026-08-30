from abc import ABC
from dataclasses import dataclass, field
from typing import final

from ...ipc import NodeManager
from ...settings import StatusCodes as scs


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
        self.ds_safe_lag = cfgDS.safe_lag
        self.ds_cell_amount = cfgDS.cell_amount
        self.ds_data_size = cfgDS.data_size
        self.ds_data_header_size = cfgDS.data_header_size
        self.ds_data = cfgDS.data.view
        self.ds_data_header = cfgDS.data_header.view
        self.ds_wid = cfgDS.writer_id.view.cast("q")
        self.ds_rid = cfgDS.reader_id.view.cast("q")

        cfgGUS = self.manager.cfgGetUserStream
        self.gus_safe_lag = cfgGUS.safe_lag
        self.gus_cell_amount = cfgGUS.cell_amount
        self.gus_data_size = cfgGUS.data_size
        self.gus_data_header_size = cfgGUS.data_header_size
        self.gus_data = cfgGUS.data.view
        self.gus_data_header = cfgGUS.data_header.view
        self.gus_wid = cfgGUS.writer_id.view.cast("q")
        self.gus_rid = cfgGUS.reader_id.view.cast("q")

        cfgSUS = self.manager.cfgSetUserStream
        self.sus_safe_lag = cfgSUS.safe_lag
        self.sus_cell_amount = cfgSUS.cell_amount
        self.sus_data_size = cfgSUS.data_size
        self.sus_data_header_size = cfgSUS.data_header_size
        self.sus_data = cfgSUS.data.view
        self.sus_data_header = cfgSUS.data_header.view
        self.sus_wid = cfgSUS.writer_id.view.cast("q")
        self.sus_rid = cfgSUS.reader_id.view.cast("q")

    @final
    def lag_not_is_safe(
        self, wid: memoryview, rid: memoryview, cell_amount: int, safe_lag: int
    ) -> bool:
        return ((wid[0] - rid[0] + cell_amount) % cell_amount) > safe_lag

    @final
    def set_raw_data(
        self,
        raw_data: bytes,
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
        self.manager.set_text(" ")
