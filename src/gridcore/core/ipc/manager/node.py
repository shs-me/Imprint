"""Worker process manager interface for updating status flags and IPC communication."""

import gc
import time
from dataclasses import dataclass, field
from typing import override

from ...settings import StatusCodes as scs
from .base import Base


@dataclass(slots=True)
class Node(Base):
    """Manager instance dedicated to individual worker process status tracking and IPC signaling."""

    _proc_id: int
    _task_id: int

    _wait_main_task: bool = field(init=False)
    proc_status: memoryview = field(init=False)
    task_status: memoryview = field(init=False)

    @override
    def __post_init__(self) -> None:
        """Binds process task and status memory views matching worker ID."""
        Base.__post_init__(self)

        self._wait_main_task = False
        self.proc_status = self._procs_status[self._proc_id : self._proc_id + 1]
        self.task_status = self._procs_status[self._task_id : self._task_id + 1]

    def set_text(self, text: str) -> None:
        """Writes formatted process status text message to shared memory text buffer."""

        lag: int = (
            (self._ts_wid[self._proc_id] - self._ts_rid[self._proc_id])
            + self._ts_cell_amount
        ) % self._ts_cell_amount
        if lag > self._ts_safe_lag:
            return self.set_proc_sc(
                scs.RING_BUFFER_TEXT_STREAM_OVERFLOW, wait_main_task=False
            )

        b_text = text.encode()

        if (len(b_text) + 8) > self._ts_data_size:
            self.set_proc_sc(scs.BIG_TEXT_SIZE, wait_main_task=False)

        cell: int = self._ts_wid[self._proc_id]
        need_cell: int = (self._proc_id * self._ts_cell_amount) + cell
        self._ts_data_header[need_cell] = len(b_text)
        start: int = need_cell * self._ts_data_size
        self._ts_data[start : (start + 8)].cast("q")[0] = round(time.time() * 1000)
        self._ts_data[(start + 8) : (start + 8) + len(b_text)] = b_text
        new_cell: int = cell + 1
        self._ts_wid[self._proc_id] = new_cell if new_cell < self._ts_cell_amount else 0

        self.set_proc_sc(scs.HAVE_TEXT, wait_main_task=False)

    def have_status(self) -> bool:
        if self.proc_status[0] != 0 or self.task_status[0] != 0:
            if (
                not (self.proc_status[0] == scs.HAVE_TEXT.value)
                or self.task_status[0] != 0
            ):
                return True

        return False

    def check_base_task(self) -> int:
        if self.task_status[0] != 0 or self.proc_status[0] != 0:
            if self._wait_main_task:
                while self.task_status[0] == 0:
                    time.sleep(0)

                self._wait_main_task = False

            task_sc: int = self.task_status[0]
            return_data: int = task_sc
            clear_task: int = 0

            if task_sc & scs.RUN:
                clear_task |= scs.RUN

            if task_sc & scs.STOP:
                self._general_event.wait()
                clear_task |= scs.STOP

            if task_sc & scs.GC_COLLECT:
                gc.collect()
                clear_task |= scs.GC_COLLECT

            if clear_task:
                self._clear_task_sc(clear_task)

            return return_data

        else:
            return False

    def set_proc_sc(self, code: scs | int, wait_main_task: bool) -> None:
        """Sets status code bitmask for process and signals MainManager semaphore."""

        self.proc_status[0] |= code
        self._main_status[self._proc_id] += 1
        self._sc_sem.release()
        if not self._wait_main_task:
            self._wait_main_task = wait_main_task

    def _set_task_sc(self, code: scs | int) -> None:
        """Sets task status code bitmask for assigned task slot."""

        self.task_status[0] |= code

    def _clear_task_sc(self, code: scs | int) -> None:
        """Clears task status code bitmask flags."""

        self.task_status[0] &= ~(code)
