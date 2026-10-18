"""Main process manager tracking worker process health and orchestrating tasks.

This module provides the central Host orchestrator manager that runs a supervision loop,
interprets incoming status codes, manages logs across worker streams, and coordinates graceful shutdowns.
"""

import time
from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import final, override

from loguru import logger

from imprint._core.ipc.manager.base import Base
from imprint._core.settings import LogLevel, ProcsIds
from imprint._core.settings import StatusCodes as scs
from imprint._core.types import ProcsData


@dataclass(slots=True)
class Host(Base):
    """Supervise worker process health and handle process status codes."""

    last_gc_time: float = field(default_factory=lambda: time.time(), init=False)
    """Epoch timestamp of the last executed garbage collection run."""

    gc_timer: int = field(default=60 * 30, init=False)
    """Interval in seconds between periodic garbage collection triggers, default is 1800 seconds."""

    time_format: str = field(init=False)
    """The logging timestamp format, adjusted automatically if backtesting is active."""

    close_procs: bool = field(default=False, init=False)
    close_core: bool = field(default=False, init=False)
    procs: dict[int, ProcsData] = field(init=False)

    @override
    def _post_init(self) -> None:
        self.time_format = (
            "%H:%M:%S.%f"
            if self.cfgSetup.is_backtesting
            else "%Y:%m:%d-%H:%M:%S.%f"
        )

    def run(self, procs: dict[int, ProcsData]) -> None:
        """Run supervisor loop waiting on process semaphores and handling status code events."""
        self.procs = procs
        # - - -
        while True:
            if bool(len(procs)):
                self._sc_sem.acquire(timeout=30)
                self.garbage_collect()
                self.check_process_status_code()
                if self.close_procs:
                    self.kill_procs()
                    self.close_core = True

                if self.close_core:
                    return
            else:
                return

    def garbage_collect(self) -> None:
        """Trigger garbage collection on worker processes periodically based on elapsed time."""
        if (now := time.time()) > (self.last_gc_time + self.gc_timer):
            self.set_task_sc_to_proc(scs.GC_COLLECT)
            self.last_gc_time = now

    def check_process_status_code(self) -> None:
        """Examine status buffers for each monitored worker and handle outstanding code changes."""
        if self._get_sc(ProcsIds.streaming):
            self.check_streaming_proc()

        if self._get_sc(ProcsIds.engine):
            self.check_engine_proc()

        if self.cfgSetup.with_execution and self._get_sc(ProcsIds.executing):
            self.check_executing_proc()

    def check_streaming_proc(self) -> None:
        """Examine streaming worker process data flags and manage pipeline data states."""
        if not self.procs.get(ProcsIds.streaming):
            return

        pid, p_name, tid, sc = self.get_proc_data(ProcsIds.streaming)

        self.action_for_base_sc(sc, pid, tid, p_name)

        if sc & scs.DATA_PREPARED:
            self.set_task_sc_to_proc(scs.COMPLETE)
            self._clear_sc(pid, scs.DATA_PREPARED)
            self.logger(scs.DATA_PREPARED.label, LogLevel.SUCCESS, p_name)

        if sc & scs.BIG_RAW_DATA:
            self._clear_sc(pid, scs.BIG_RAW_DATA)
            self.logger(scs.BIG_RAW_DATA.label, LogLevel.WARNING, p_name)
            self.close_procs = True

        self.proc_is_alive(pid)

    def check_engine_proc(self) -> None:
        """Examine calculation engine worker flags and manage calculation/indicator feedback."""
        if not self.procs.get(ProcsIds.engine):
            return

        pid, p_name, tid, sc = self.get_proc_data(ProcsIds.engine)

        self.action_for_base_sc(sc, pid, tid, p_name)

        if sc & scs.FP_IDX_FILLED:
            self._clear_sc(pid, scs.FP_IDX_FILLED)
            self.logger(scs.FP_IDX_FILLED.label, LogLevel.DEBUG, p_name)

        if sc & scs.FP_IDY_FILLED:
            self._clear_sc(pid, scs.FP_IDY_FILLED)
            self.logger(scs.FP_IDY_FILLED.label, LogLevel.DEBUG, p_name)

        if sc & scs.FP_RE_INIT:
            self._clear_sc(pid, scs.FP_RE_INIT)
            self.logger(scs.FP_RE_INIT.label, LogLevel.DEBUG, p_name)

        if sc & scs.BIG_GAP:
            self._clear_sc(pid, scs.BIG_GAP)
            self.logger(scs.BIG_GAP.label, LogLevel.ERROR, p_name)
            self.close_procs = True

        if sc & scs.ANALYSIS_LAG_MORE_SAFE_LAG:
            self._clear_sc(pid, scs.ANALYSIS_LAG_MORE_SAFE_LAG)
            self.logger(
                scs.ANALYSIS_LAG_MORE_SAFE_LAG.label, LogLevel.WARNING, p_name
            )

        self.proc_is_alive(pid)

    def check_executing_proc(self) -> None:
        """Examine executing worker flags and handle execution boundary issues."""
        if not self.procs.get(ProcsIds.executing):
            return

        pid, p_name, tid, sc = self.get_proc_data(ProcsIds.executing)

        self.action_for_base_sc(sc, pid, tid, p_name)

        if sc & scs.LOSS_MORE_LIMIT:
            self._clear_sc(pid, scs.LOSS_MORE_LIMIT)
            self.logger(scs.LOSS_MORE_LIMIT.label, LogLevel.WARNING, p_name)
            self.close_procs = True

        if sc & scs.QTY_LESS_LIMIT:
            self._clear_sc(pid, scs.QTY_LESS_LIMIT)
            self.logger(scs.QTY_LESS_LIMIT.label, LogLevel.WARNING, p_name)
            self.close_procs = True

        if sc & scs.ORDER_LIMIT:
            self._clear_sc(pid, scs.ORDER_LIMIT)
            self.logger(scs.ORDER_LIMIT.label, LogLevel.WARNING, p_name)
            self.close_procs = True

        self.proc_is_alive(pid)

    def action_for_base_sc(
        self, sc: int, pid: int, tid: int, proc_name: str
    ) -> None:
        """Execute basic state resolutions and system signaling for shared status codes."""

        if sc & scs.HAVE_LOG:
            self._clear_sc(pid, scs.HAVE_LOG)
            for timestamp, level, log in self.get_log(pid):
                self.logger(log, LogLevel(level), proc_name, timestamp)

        if sc & scs.STOP:
            self.set_task_sc_to_proc(scs.RUN, tid)
            if self.procs_have_task_sc(scs.RUN):
                self.general_event(True)

            self._clear_sc(pid, scs.STOP)
            self.logger(scs.STOP.label, LogLevel.DEBUG, proc_name)

        if sc & scs.RUN:
            self._clear_sc(pid, scs.RUN)
            self.logger(scs.RUN.label, LogLevel.DEBUG, proc_name)

        if sc & scs.ERROR:
            self._clear_sc(pid, scs.ERROR)
            self.logger(scs.ERROR.label, LogLevel.ERROR, proc_name)
            self.close_procs = True

        if sc & scs.EXIT:
            self._clear_sc(pid, scs.EXIT)
            self.procs.pop(pid)
            self.logger(scs.EXIT.label, LogLevel.SUCCESS, proc_name)

        if sc & scs.COMPLETE:
            if self._config_idx == self._count_configs:
                self.set_task_sc_to_proc(scs.EXIT, tid)
            else:
                self.general_event(False)
                self.set_task_sc_to_proc(scs.RESET, tid)

            self._clear_sc(pid, scs.COMPLETE)
            self.logger(scs.COMPLETE.label, LogLevel.DEBUG, proc_name)

        if sc & scs.RESET:
            self.set_task_sc_to_proc(scs.RUN, tid)
            self._clear_sc(pid, scs.RESET)
            self.logger(scs.RESET.label, LogLevel.DEBUG, proc_name)
            if self.procs_have_task_sc(scs.RUN):
                self._change_configs()
                self._reset()
                self.general_event(True)
                self.logger("RESET\n", LogLevel.DEBUG)

        if sc & scs.INVALID_DATA:
            self._clear_sc(pid, scs.INVALID_DATA)
            self.logger(scs.INVALID_DATA.label, LogLevel.ERROR, proc_name)
            self.close_procs = True

        if sc & scs.DECODE_ERROR:
            self._clear_sc(pid, scs.DECODE_ERROR)
            self.logger(scs.DECODE_ERROR.label, LogLevel.ERROR, proc_name)
            self.close_procs = True

        if sc & scs.ENCODE_ERROR:
            self._clear_sc(pid, scs.ENCODE_ERROR)
            self.logger(scs.ENCODE_ERROR.label, LogLevel.ERROR, proc_name)
            self.close_procs = True

        if sc & scs.BIG_LOG_SIZE:
            self._clear_sc(pid, scs.BIG_LOG_SIZE)
            self.logger(scs.BIG_LOG_SIZE.label, LogLevel.WARNING, proc_name)

        if sc & scs.RING_BUFFER_LOG_STREAM_OVERFLOW:
            self._clear_sc(pid, scs.RING_BUFFER_LOG_STREAM_OVERFLOW)
            self.logger(
                scs.RING_BUFFER_LOG_STREAM_OVERFLOW.label,
                LogLevel.WARNING,
                proc_name,
            )

    def procs_have_task_sc(self, sc: int) -> bool:
        return all(
            (self._get_sc(v["task_id"]) & sc) for v in self.procs.values()
        )

    def get_proc_data(self, proc: int) -> tuple[int, str, int, int]:
        """Fetch status and identity details for a given process key.

        Returns
        -------
        tuple of (int, str, int, int)
            A tuple containing ``(process_id, process_name, task_id, status_code)``.
        """
        pid: int = proc
        p_name: str = self.procs[pid]["proc_name"]
        tid: int = self.procs[pid]["task_id"]
        p_sc: int = self._get_sc(pid)
        return pid, p_name, tid, p_sc

    def set_task_sc_to_proc(self, code: scs, tid: int | None = None) -> None:
        """Dispatch task status code to specified task slot or all active processes.

        If tid is None, targets all active processes.
        """
        for v in self.procs.values():
            if (v["task_id"] == tid) or (tid is None):
                self._set_sc(v["task_id"], code)

    def proc_is_alive(self, pid: int) -> None:
        """Verify process vitality and switch the shutdown flag if dead."""
        if (
            self.procs.get(pid)
            and not self._sc_sem.get_value()
            and not self.procs[pid]["proc"].is_alive()
        ):
            self.logger(
                "Process is dead.",
                LogLevel.CRITICAL,
                self.procs[pid]["proc_name"],
            )
            self.close_procs = True

    def kill_procs(self) -> None:
        """Terminate and join all active worker processes."""
        for v in self.procs.values():
            if v["proc"].is_alive():
                v["proc"].terminate()
                v["proc"].join()

            self.logger(scs.TERMINATE.label, LogLevel.WARNING, v["proc_name"])

    def general_event(self, run: bool, tids: list[int] | None = None) -> None:
        """Set or clear general synchronization event across worker tasks.

        If run is false and tids is provided, sets STOP status code.
        """
        if run:
            if not self._general_event.is_set():
                self._general_event.set()
        else:
            if self._general_event.is_set():
                self._general_event.clear()

            if tids:
                [self._set_sc(tid, scs.STOP) for tid in tids]

    def get_log(self, pid: int) -> Generator[tuple[int, int, str]]:
        """Retrieve and decode log status message for specified process ID.

        Returns
        -------
        Generator[tuple[int, int, str]]
            Generator of logs formatted as ``(timestamp, level, plaintext_log)``.
        """
        _ = self.mlLogStream.ring_buf
        # - - -
        while _.rid_buf[pid] != _.wid_buf[pid]:
            cell: int = _.rid_buf[pid]
            need_cell: int = (pid * _.cell_amount) + cell
            start: int = need_cell * _.cell_size
            lrd: int = _.data_header_buf[need_cell]

            headers: memoryview = _.data_buf[
                start : (start := (start + 16))
            ].cast("q")
            timestamp, level = headers[0], headers[1]
            msg: str = bytes(_.data_buf[start : (start + lrd)]).decode()

            new_cell: int = cell + 1
            _.rid_buf[pid] = new_cell if new_cell < _.cell_amount else 0
            yield timestamp, level, msg

    def logger(
        self,
        message: str,
        level: LogLevel,
        proc_name: str = "HOST",
        timestamp: int | None = None,
    ) -> None:
        """Log data using loguru.

        If pass_debug_logs is enabled and log level is DEBUG, the log is discarded.
        If a timestamp is provided, it is used for date/time generation; otherwise current time is used.
        """
        if self.cfgSetup.pass_debug_logs and (level == LogLevel.DEBUG):
            return

        t = timestamp / 1000 if timestamp else time.time()
        log = logger.bind(
            time=datetime.fromtimestamp(t, tz=UTC).strftime(self.time_format),
            level=level.name,
            proc_name=proc_name,
        )
        log.info(message)


@final
@dataclass(slots=True)
class HostManager(Host): ...  # pyright: ignore[reportUninitializedInstanceVariable]
