"""Worker process IPC manager and signaling node.

Provides status reporting, ring-buffered logging, task-status bitmask
manipulation, exception dumps, and error decorator routines tailored for worker processes.
"""

import gc
import time
from dataclasses import dataclass, field
from typing import Any, final, override

from imprint._core.ipc.manager.base import Base
from imprint._core.settings import LogLevel
from imprint._core.settings import StatusCodes as scs


@dataclass(slots=True)
class Node(Base):
    """Worker process manager.

    Responsible for communication with the main process, handling host tasks and
    sending process tasks to the host. Writes custom logs to the ring buffer
    for subsequent host logging. Inherits configuration and memory layout storage
    from the base manager.
    """

    _pid: int
    _tid: int

    __wait_main_task: bool = field(default=False, init=False)
    __ignore_ps: int = field(
        default=~(
            scs.RUN
            | scs.HAVE_LOG
            | scs.BIG_LOG_SIZE
            | scs.RING_BUFFER_LOG_STREAM_OVERFLOW
            | scs.FP_RE_INIT
            | scs.FP_IDX_FILLED
            | scs.FP_IDY_FILLED
            | scs.ANALYSIS_LAG_MORE_SAFE_LAG
        ),
        init=False,
    )
    """Process status codes ignored by the manager."""

    __alowed_ts: int = field(
        default=(scs.RUN | scs.STOP | scs.RESET | scs.GC_COLLECT), init=False
    )
    """Host tasks handled by the manager."""

    def set_log(self, msg: Any, level: LogLevel = LogLevel.INFO, /) -> None:
        """Transmit logs to the host as a high-performance logging alternative.

        - Each process has a fixed ring buffer size for logging.
        - The logged object must be serializable to str.
        - If the log size exceeds the buffer cell size, it is discarded and the
        host is notified via BIG_LOG_SIZE.
        - If the buffer is full and the host cannot keep up, the log is discarded
        and the host is notified via RING_BUFFER_LOG_STREAM_OVERFLOW.
        - If pass_debug_logs is enabled, all DEBUG level logs are discarded.
        - Timestamps are generated locally rather than by the host, which may
        introduce minor chronological discrepancies.
        - Upon successful write, the host is notified via HAVE_LOG.
        """
        if self.cfgSetup.pass_debug_logs and (level == LogLevel.DEBUG):
            return

        _ = self.mlLogStream.ring_buf
        lag: int = (
            (_.wid_buf[self._pid] - _.rid_buf[self._pid]) + _.cell_amount
        ) % _.cell_amount
        if lag > _.safe_lag:
            return self.set_proc_sc(
                scs.RING_BUFFER_LOG_STREAM_OVERFLOW, wait_main_task=False
            )

        b_log: bytes = str(msg).encode()
        if (len(b_log) + 8) > _.cell_size:
            return self.set_proc_sc(scs.BIG_LOG_SIZE, wait_main_task=False)

        cell: int = _.wid_buf[self._pid]
        need_cell: int = (self._pid * _.cell_amount) + cell
        start: int = need_cell * _.cell_size

        headers: memoryview = _.data_buf[start : (start := (start + 16))].cast(
            "q"
        )
        headers[0], headers[1] = round(time.time() * 1000), level
        _.data_buf[start : (start + len(b_log))] = b_log
        _.data_header_buf[need_cell] = len(b_log)

        new_cell: int = cell + 1
        _.wid_buf[self._pid] = new_cell if new_cell < _.cell_amount else 0

        self.set_proc_sc(scs.HAVE_LOG, wait_main_task=False)

    def set_proc_sc(self, code: scs, wait_main_task: bool) -> None:
        self._set_sc(self._pid, code)
        self._sc_sem.release()
        if not self.__wait_main_task:
            self.__wait_main_task = wait_main_task

    def get_task_sc(self) -> int | None:
        """Check for unignored host or process task flags.

        If host tasks are absent but process tasks are present and main task
        waiting is enabled, waits in an infinite loop with 1ms timeouts until the
        host assigns a task.
        If host tasks are present, processes base tasks and returns the task flag
        (including processed tasks). Otherwise returns None.
        """
        proc_sc, task_sc = self._get_sc(self._pid), self._get_sc(self._tid)
        if (task_sc != 0) or (
            (proc_sc != 0) and (proc_sc & self.__ignore_ps) != 0
        ):
            return self.__check_base_task()

    def __check_base_task(self) -> int:
        """Return host task flags and handle base tasks:

        - RUN: Cleared directly.
        - STOP: Notifies successful stop via STOP, waits on Event, notifies RUN.
        - RESET: Updates configs, runs garbage collection, notifies RESET, waits on Event, notifies RUN.
        - GC_COLLECT: Runs garbage collection.

        Processed tasks are cleared from the returned task flag.
        If main task waiting is enabled, waits in an infinite loop with 1ms timeouts until the host assigns a task.
        """
        if self.__wait_main_task:
            while self._get_sc(self._tid) == 0:
                time.sleep(0.001)

            self.__wait_main_task = False

        task_sc: int = self._get_sc(self._tid)

        if task_sc & self.__alowed_ts:
            clear_task: int = 0

            if task_sc & scs.RUN:
                clear_task |= scs.RUN

            if task_sc & scs.STOP:
                self.set_proc_sc(scs.STOP, wait_main_task=False)
                self._general_event.wait()
                self.set_proc_sc(scs.RUN, wait_main_task=False)
                clear_task |= scs.STOP

            if task_sc & scs.RESET:
                self._change_configs()
                gc.collect()
                self.set_proc_sc(scs.RESET, wait_main_task=False)
                self._general_event.wait()
                self.set_proc_sc(scs.RUN, wait_main_task=False)
                clear_task |= scs.RESET

            if task_sc & scs.GC_COLLECT:
                gc.collect()
                clear_task |= scs.GC_COLLECT

            if clear_task:
                self._clear_sc(self._tid, clear_task)

        return task_sc

    def complete(self) -> None:
        """Notify the host of successful work completion (COMPLETE)."""
        self._clear_sc(self._tid, scs.COMPLETE)
        self.set_proc_sc(scs.COMPLETE, wait_main_task=True)

    def dump_exc(self, set_status_code_error: bool = False, /) -> None:
        """Serialize current system exception traceback and locals to disk."""
        self._dumper.dump_exception()
        if set_status_code_error:
            self.set_proc_sc(scs.ERROR, wait_main_task=set_status_code_error)

    @override
    def _child_exit_action(self) -> None:
        if self._dumper.exc_tb:
            self.set_proc_sc(scs.ERROR, wait_main_task=True)


@final
@dataclass(slots=True)
class NodeManager(Node): ...  # pyright: ignore[reportUninitializedInstanceVariable]
