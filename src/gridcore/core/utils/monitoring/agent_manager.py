"""Worker process manager interface for updating status flags and IPC communication."""

import gc
import time

from ...settings import StatusCodes as scs
from .base_manager import Manager


class AgentManager(Manager):
    """Manager instance dedicated to individual worker process status tracking and IPC signaling."""

    def __init__(
        self,
        segments: dict[str, slice],
        shm_buf: memoryview,
        configs: list,
        main_tools: list,
        proc_id: int,
        task_id: int,
    ) -> None:
        """Binds process task and status memory views matching worker ID."""

        super().__init__(segments, shm_buf, configs, main_tools)

        self._proc_id: int = proc_id
        self._task_id: int = task_id

        self._wait_main_task: bool = False
        self.proc_status: memoryview = self._procs_status[proc_id : proc_id + 1]
        self.task_status: memoryview = self._procs_status[task_id : task_id + 1]

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
            if not (self.proc_status[0] == scs.HAVE_TEXT) or self.task_status[0] != 0:
                return True

        return False

    def check_base_task(self, complete: bool) -> bool | int:
        """Evaluates task status flags set by MainManager and executes task commands.

        Args:
            complete (bool): True if worker process has completed pipeline work.

        Returns:
            bool | int: Task action indicator or task status code.
        """

        if self.task_status[0] != 0 or self.proc_status[0] != 0:
            if self._wait_main_task:
                while self.task_status[0] == 0:
                    time.sleep(0)

                self._wait_main_task = False

            task_sc: int = self.task_status[0]
            _return_data, _clear_task, _set_proc_sc = task_sc, True, None

            if task_sc & scs.RUN:
                _return_data = False

            if task_sc & scs.STOP:
                self._general_event.wait()
                _return_data = False

            if task_sc & scs.EXIT:
                _return_data, _clear_task, _set_proc_sc = True, False, scs.EXIT

            if task_sc & scs.COMPLETE:
                _return_data, _clear_task = (
                    (True, False) if complete else (False, False)
                )

            if task_sc & scs.GC_COLLECT:
                gc.collect()
                _return_data = False

            if task_sc & (scs.QTY_LESS_LIMIT | scs.LOSS_MORE_LIMIT):
                _return_data = True

            if _clear_task:
                self.clear_task_sc(task_sc)

            if _set_proc_sc:
                self.set_proc_sc(_set_proc_sc, wait_main_task=True)

            return _return_data

        else:
            return False

    def set_proc_sc(self, code: scs | int, wait_main_task: bool) -> None:
        """Sets status code bitmask for process and signals MainManager semaphore."""

        self.proc_status[0] |= code
        self._main_status[self._proc_id] += 1
        self._sc_sem.release()
        if not self._wait_main_task:
            self._wait_main_task = wait_main_task

    def set_task_sc(self, code: scs | int) -> None:
        """Sets task status code bitmask for assigned task slot."""

        self.task_status[0] |= code

    def clear_task_sc(self, code: scs | int) -> None:
        """Clears task status code bitmask flags."""

        self.task_status[0] &= ~(code)
