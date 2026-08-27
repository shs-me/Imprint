import time
from abc import ABC

from ...ipc import NodeManager
from ...settings import StatusCodes as scs


class Base(ABC):
    def __init__(self, manager: NodeManager) -> None:
        self.manager: NodeManager = manager

        cfgDS = self.manager.cfgDataStream
        self.ds_safe_lag: int = cfgDS.safe_lag
        self.ds_cell_amount: int = cfgDS.cell_amount
        self.ds_data_size: int = cfgDS.data_size
        self.ds_data_header_size: int = cfgDS.data_header_size
        self.ds_data: memoryview = cfgDS.data.view
        self.ds_data_header: memoryview = cfgDS.data_header.view
        self.ds_wid: memoryview = cfgDS.writer_id.view.cast("q")
        self.ds_rid: memoryview = cfgDS.reader_id.view.cast("q")

        cfgGUS = self.manager.cfgGetUserStream
        self.gus_safe_lag: int = cfgGUS.safe_lag
        self.gus_cell_amount: int = cfgGUS.cell_amount
        self.gus_data_size: int = cfgGUS.data_size
        self.gus_data_header_size: int = cfgGUS.data_header_size
        self.gus_data: memoryview = cfgGUS.data.view
        self.gus_data_header: memoryview = cfgGUS.data_header.view
        self.gus_wid: memoryview = cfgGUS.writer_id.view.cast("q")
        self.gus_rid: memoryview = cfgGUS.reader_id.view.cast("q")

        cfgSUS = self.manager.cfgSetUserStream
        self.sus_safe_lag: int = cfgSUS.safe_lag
        self.sus_cell_amount: int = cfgSUS.cell_amount
        self.sus_data_size: int = cfgSUS.data_size
        self.sus_data_header_size: int = cfgSUS.data_header_size
        self.sus_data: memoryview = cfgSUS.data.view
        self.sus_data_header: memoryview = cfgSUS.data_header.view
        self.sus_wid: memoryview = cfgSUS.writer_id.view.cast("q")
        self.sus_rid: memoryview = cfgSUS.reader_id.view.cast("q")

    def alarm_clock(
        self, wid: memoryview, rid: memoryview, cell_amount: int, safe_lag: int
    ) -> None:
        while ((wid[0] - rid[0] + cell_amount) % cell_amount) > safe_lag:
            time.sleep(0)

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

    def final_actions(self) -> None:
        self.manager.set_text(" ")
