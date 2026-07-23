import time
from abc import ABC

from ...utils.monitoring.agent_manager import AgentManager
from ...utils.monitoring.status_codes import StatusCodes as scs


class Wss(ABC):
    def __init__(self, manager: AgentManager) -> None:
        self.manager: AgentManager = manager
        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status, self.proc_status = manager.task_status, manager.proc_status

        cfgDS = self.manager.cfgDataStream
        self.safe_lag: int = cfgDS.safe_lag
        self.cell_amount: int = cfgDS.cell_amount
        self.data_size: int = cfgDS.data_size
        self.data_header_size: int = cfgDS.data_header_size
        self.data: memoryview = cfgDS.data
        self.data_header: memoryview = cfgDS.data_header
        self.wCellC: memoryview = cfgDS.writer_id.cast("q")
        self.rCellC: memoryview = cfgDS.reader_id.cast("q")

    def alarm_clock(
        self, wCellC: memoryview, rCellC: memoryview, cell_amount: int, safe_lag: int
    ) -> None:
        while ((wCellC[0] - rCellC[0] + cell_amount) % cell_amount) > safe_lag:
            time.sleep(0)

    def set_raw_data(
        self,
        raw_data: bytes,
        data: memoryview,
        data_header: memoryview,
        wCellC: memoryview,
        cell_amount: int,
        data_size: int,
    ) -> bool:
        if (lrd := len(raw_data)) < data_size:
            cell: int = wCellC[0]
            data_header[cell] = lrd
            start: int = cell * data_size
            data[start : start + lrd] = raw_data
            new_cell = cell + 1
            wCellC[0] = new_cell if new_cell < cell_amount else 0
            return True
        else:
            self.set_proc_sc(code=scs.BIG_RAW_DATA)
            return False

    def final_actions(self) -> None:
        self.set_proc_sc(scs.COMPLETE)
