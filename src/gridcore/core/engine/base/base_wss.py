"""Abstract network and stream ingestion process template."""

import time
from abc import ABC

from ...settings import StatusCodes as scs
from ...utils.monitoring.agent_manager import AgentManager


class Wss(ABC):
    """Base class providing ring buffer write routines for stream connections."""

    def __init__(self, manager: AgentManager) -> None:
        """Binds DataStream shared memory views and buffer parameters."""

        self.manager: AgentManager = manager
        self.set_proc_sc = manager.set_proc_sc
        self.have_status = manager.have_status
        self.task_status = manager.task_status
        self.check_base_task = manager.check_base_task

        cfgDS = self.manager.cfgDataStream
        self.ds_safe_lag: int = cfgDS.safe_lag
        self.ds_cell_amount: int = cfgDS.cell_amount
        self.ds_data_size: int = cfgDS.data_size
        self.ds_data_header_size: int = cfgDS.data_header_size
        self.ds_data: memoryview = cfgDS.data
        self.ds_data_header: memoryview = cfgDS.data_header
        self.ds_wid: memoryview = cfgDS.writer_id.cast("q")
        self.ds_rid: memoryview = cfgDS.reader_id.cast("q")

        cfgGUS = self.manager.cfgGetUserStream
        self.gus_safe_lag: int = cfgGUS.safe_lag
        self.gus_cell_amount: int = cfgGUS.cell_amount
        self.gus_data_size: int = cfgGUS.data_size
        self.gus_data_header_size: int = cfgGUS.data_header_size
        self.gus_data: memoryview = cfgGUS.data
        self.gus_data_header: memoryview = cfgGUS.data_header
        self.gus_wid: memoryview = cfgGUS.writer_id.cast("q")
        self.gus_rid: memoryview = cfgGUS.reader_id.cast("q")

        cfgSUS = self.manager.cfgSetUserStream
        self.sus_safe_lag: int = cfgSUS.safe_lag
        self.sus_cell_amount: int = cfgSUS.cell_amount
        self.sus_data_size: int = cfgSUS.data_size
        self.sus_data_header_size: int = cfgSUS.data_header_size
        self.sus_data: memoryview = cfgSUS.data
        self.sus_data_header: memoryview = cfgSUS.data_header
        self.sus_wid: memoryview = cfgSUS.writer_id.cast("q")
        self.sus_rid: memoryview = cfgSUS.reader_id.cast("q")

    def alarm_clock(
        self, wid: memoryview, rid: memoryview, cell_amount: int, safe_lag: int
    ) -> None:
        """Throttles intake stream writing if DataStream ring buffer unread cell lag exceeds limit."""

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
        """Writes raw binary packet into ring buf cell and advances writer position.

        Returns:
            bool: True if payload size fits within cell capacity.
        """

        if (lrd := len(raw_data)) < data_size:
            cell: int = writer_id[0]
            data_header[cell] = lrd
            start: int = cell * data_size
            data[start : start + lrd] = raw_data
            new_cell = cell + 1
            writer_id[0] = new_cell if new_cell < cell_amount else 0
            return True
        else:
            self.set_proc_sc(code=scs.BIG_RAW_DATA)
            return False

    def final_actions(self) -> None:
        """Sets completion process status code upon connection close."""
        self.manager.set_text(" ")
