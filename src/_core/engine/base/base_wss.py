import time
from abc import ABC

from ...utils.monitoring.agent_manager import AgentManager
from ...utils.monitoring.status_codes import StatusCodes as scs


class Wss(ABC):
    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager

        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status, self.proc_status = manager.task_status, manager.proc_status

        cfgRaw = self.manager.cfgRaw
        self.data_size: int = cfgRaw.data_size
        self.header_size: int = cfgRaw.header_size
        self.data_offset: int = cfgRaw.data[0]
        self.dataHeader_offset: int = cfgRaw.dataHeader[0]
        self.cell_amount: int = cfgRaw.cell_amount
        self.safe_lag: int = cfgRaw.safe_lag
        self.wCellC: memoryview[int] = self.manager.raw_buf[
            slice(*cfgRaw.WriterCellCounter)
        ].cast("q")
        self.rCellC: memoryview[int] = self.manager.raw_buf[
            slice(*cfgRaw.ReaderCellCounter)
        ].cast("q")

    def alarm_clock(
        self, wCellC: memoryview, rCellC: memoryview, cell_amount: int, safe_lag: int
    ) -> None:
        while ((wCellC[0] - rCellC[0] + cell_amount) % cell_amount) > safe_lag:
            time.sleep(0)

    def set_raw_data(
        self,
        raw_data: bytes,
        raw_buf: memoryview,
        wCellC: memoryview,
        cell_amount: int,
        data_size: int,
        data_offset: int,
        dataHeader_offset: int,
    ) -> bool:
        if (lrd := len(raw_data)) < data_size:
            cell: int = wCellC[0]

            raw_buf[cell + dataHeader_offset] = lrd
            start: int = cell * data_size + data_offset
            raw_buf[start : start + lrd] = raw_data

            new_cell = cell + 1
            wCellC[0] = new_cell if new_cell < cell_amount else 0
            return True
        else:
            self.set_proc_sc(code=scs.BIG_RAW_DATA)
            return False

    def final_actions(self) -> None:
        self.set_proc_sc(scs.COMPLETE)
