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
        self._proc_spec_id: int = 1 << self._proc_id

        self.task_status: memoryview = self.cfgMetrics.status.cast("q")[
            task_id : task_id + 1
        ]
        self.proc_status: memoryview = self.cfgMetrics.status.cast("q")[
            proc_id : proc_id + 1
        ]

    def set_text(self, text: str) -> None:
        """Writes formatted process status text message to shared memory text buffer."""

        text_buf: memoryview = self.cfgMetrics.text
        b_text, start = text.encode(), self._proc_id * self.cfgMetrics.text_size
        set_len, start = text_buf[start : start + 8].cast("q"), start + 8
        set_len[0] = len(b_text)
        text_buf[start : start + len(b_text)] = b_text

    def check_base_task(self, complete: bool) -> bool | int:
        """Evaluates task status flags set by MainManager and executes task commands.

        Args:
            complete (bool): True if worker process has completed pipeline work.

        Returns:
            bool | int: Task action indicator or task status code.
        """

        if self.task_status[0] != 0 or self.proc_status[0] != 0:
            while self.task_status[0] == 0:
                time.sleep(0)

            task_sc: int = self.task_status[0]
            _return_data, _clear_task, _set_proc_sc = task_sc, True, None

            if task_sc & scs.RUN:
                _return_data = False

            elif task_sc & scs.STOP:
                self._general_event.wait()
                _return_data = False

            elif task_sc & scs.EXIT:
                _return_data, _clear_task, _set_proc_sc = True, False, scs.EXIT

            elif task_sc & scs.COMPLETE:
                _return_data, _clear_task = (
                    (True, False) if complete else (False, False)
                )

            elif task_sc & scs.GC_COLLECT:
                gc.collect()
                _return_data = False

            elif task_sc & (scs.QTY_LESS_LIMIT | scs.LOSS_MORE_LIMIT):
                _return_data = True

            if _clear_task:
                self.clear_task_sc(task_sc)

            if _set_proc_sc:
                self.set_proc_sc(_set_proc_sc)

            return _return_data

        else:
            return False

    def set_proc_sc(self, code: scs | int) -> None:
        """Sets status code bitmask for process and signals MainManager semaphore."""

        self.proc_status[0] |= code
        self._main_status[0] |= self._proc_spec_id
        self._sc_sem.release()

    def set_task_sc(self, code: scs | int) -> None:
        """Sets task status code bitmask for assigned task slot."""

        self.task_status[0] |= code

    def clear_task_sc(self, code: scs | int) -> None:
        """Clears task status code bitmask flags."""

        self.task_status[0] &= ~(code)
