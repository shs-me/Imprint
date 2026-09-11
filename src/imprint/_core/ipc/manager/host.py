"""Main process manager tracking worker process health and orchestrating tasks."""

import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import override

from loguru import logger

from imprint._core.ipc.manager.base import Base
from imprint._core.settings import LogLevel, ProcsIds
from imprint._core.settings import StatusCodes as scs
from imprint._core.types import ProcsData


@dataclass(slots=True)
class Host(Base):
    """Central status manager monitoring worker process health and handling process status codes."""

    with_execution: bool = field(init=False)
    startDate: date = field(init=False)
    time_format: str = field(init=False)
    close_procs: bool = field(default=False, init=False)
    close_core: bool = field(default=False, init=False)
    procs: dict[int, ProcsData] = field(init=False)

    @override
    def __post_init__(self) -> None:
        Base.__post_init__(self)

        self.with_execution = self.cfgSetup.execution
        self.startDate = datetime.now(tz=UTC).date()
        self.time_format = (
            "%H:%M:%S.%f"
            if self.cfgSetup.backtesting
            else "%Y:%m:%d-%H:%M:%S.%f"
        )

    def run(self, procs: dict[int, ProcsData]) -> None:
        """Primary supervisor loop waiting on process semaphores and handling status code events."""

        self.procs = procs
        # - - -
        while True:
            if bool(len(procs)):
                self._sc_sem.acquire(timeout=30)

                if datetime.now(tz=UTC).date() > self.startDate:
                    self.set_task_sc_to_proc(scs.GC_COLLECT)
                    self.startDate = datetime.now(tz=UTC).date()

                self.check_process_status_code()
                if not self.close_core:
                    continue
            return

    def check_process_status_code(self) -> None:
        if self._main_status[ProcsIds.streaming]:
            self.check_data_streaming_proc()
            self._main_status[ProcsIds.streaming] -= 1

        if self._main_status[ProcsIds.engine]:
            self.check_engine_proc()
            self._main_status[ProcsIds.engine] -= 1

        if self.with_execution and self._main_status[ProcsIds.executing]:
            self.check_executing_proc()
            self._main_status[ProcsIds.executing] -= 1

        if self.close_procs:
            self.kill_procs()
            self.close_core = True

    def check_data_streaming_proc(self) -> None:
        if not self.procs.get(ProcsIds.streaming):
            return

        p_id, p_name, _p_task_id, sc = self.get_proc_data(ProcsIds.streaming)

        self.action_for_base_sc(sc, p_id, p_name)

        if sc & scs.DATA_PREPARED:
            self.logger(scs.DATA_PREPARED.label, LogLevel.WARNING, p_name)
            self.set_task_sc_to_proc(scs.COMPLETE)
            self.clear_proc_sc(scs.DATA_PREPARED, p_id)

        if sc & scs.BIG_RAW_DATA:
            self.logger(scs.BIG_RAW_DATA.label, LogLevel.WARNING, p_name)
            self.close_procs = True
            self.clear_proc_sc(scs.BIG_RAW_DATA, p_id)

        self.proc_is_alive(p_id)

    def check_engine_proc(self) -> None:
        if not self.procs.get(ProcsIds.engine):
            return

        p_id, p_name, _p_task_id, sc = self.get_proc_data(ProcsIds.engine)

        self.action_for_base_sc(sc, p_id, p_name)

        if sc & scs.FP_IDX_FILLED:
            self.logger(scs.FP_IDX_FILLED.label, LogLevel.WARNING, p_name)
            self.clear_proc_sc(scs.FP_IDX_FILLED, p_id)

        if sc & scs.FP_IDY_FILLED:
            self.logger(scs.FP_IDY_FILLED.label, LogLevel.WARNING, p_name)
            self.clear_proc_sc(scs.FP_IDY_FILLED, p_id)

        if sc & scs.FP_RE_INIT:
            self.logger(scs.FP_RE_INIT.label, LogLevel.SUCCESS, p_name)
            self.clear_proc_sc(scs.FP_RE_INIT, p_id)

        if sc & scs.ANALYSIS_LAG_MORE_SAFE_LAG:
            self.logger(
                scs.ANALYSIS_LAG_MORE_SAFE_LAG.label, LogLevel.WARNING, p_name
            )
            self.clear_proc_sc(scs.ANALYSIS_LAG_MORE_SAFE_LAG, p_id)

        self.proc_is_alive(p_id)

    def check_executing_proc(self) -> None:
        if not self.procs.get(ProcsIds.executing):
            return

        p_id, p_name, _p_task_id, sc = self.get_proc_data(ProcsIds.executing)

        self.action_for_base_sc(sc, p_id, p_name)

        if sc & scs.LOSS_MORE_LIMIT:
            self.logger(scs.LOSS_MORE_LIMIT.label, LogLevel.WARNING, p_name)
            self.close_procs = True
            self.clear_proc_sc(scs.LOSS_MORE_LIMIT, p_id)

        if sc & scs.QTY_LESS_LIMIT:
            self.logger(scs.QTY_LESS_LIMIT.label, LogLevel.WARNING, p_name)
            self.close_procs = True
            self.clear_proc_sc(scs.QTY_LESS_LIMIT, p_id)

        if sc & scs.ORDER_LIMIT:
            self.logger(scs.ORDER_LIMIT.label, LogLevel.WARNING, p_name)
            self.close_procs = True
            self.clear_proc_sc(scs.ORDER_LIMIT, p_id)

        self.proc_is_alive(p_id)

    def action_for_base_sc(self, sc: int, proc_id: int, proc_name: str) -> None:
        if sc & scs.HAVE_LOG:
            logs: list[tuple[int, str]] = self.get_log(proc_id)
            for timestamp, log in logs:
                self.logger(log, LogLevel.INFO, proc_name, timestamp)

            self.clear_proc_sc(scs.HAVE_LOG, proc_id)

        if sc & scs.ERROR:
            self.logger(scs.ERROR.label, LogLevel.ERROR, proc_name)
            self.close_procs = True
            self.clear_proc_sc(scs.ERROR, proc_id)

        if sc & scs.COMPLETE:
            self.logger(scs.COMPLETE.label, LogLevel.WARNING, proc_name)
            self.procs.pop(proc_id)
            self.clear_proc_sc(scs.COMPLETE, proc_id)

        if sc & scs.INVALID_DATA:
            self.logger(scs.INVALID_DATA.label, LogLevel.ERROR, proc_name)
            self.close_procs = True
            self.clear_proc_sc(scs.INVALID_DATA, proc_id)

        if sc & scs.DECODE_ERROR:
            self.logger(scs.DECODE_ERROR.label, LogLevel.ERROR, proc_name)
            self.close_procs = True
            self.clear_proc_sc(scs.DECODE_ERROR, proc_id)

        if sc & scs.ENCODE_ERROR:
            self.logger(scs.ENCODE_ERROR.label, LogLevel.ERROR, proc_name)
            self.close_procs = True
            self.clear_proc_sc(scs.ENCODE_ERROR, proc_id)

        if sc & scs.BIG_LOG_SIZE:
            self.logger(scs.BIG_LOG_SIZE.label, LogLevel.WARNING, proc_name)
            self.clear_proc_sc(scs.BIG_LOG_SIZE, proc_id)

        if sc & scs.RING_BUFFER_LOG_STREAM_OVERFLOW:
            self.logger(
                scs.RING_BUFFER_LOG_STREAM_OVERFLOW.label,
                LogLevel.WARNING,
                proc_name,
            )
            self.clear_proc_sc(scs.RING_BUFFER_LOG_STREAM_OVERFLOW, proc_id)

    def get_proc_data(self, proc: int) -> tuple[int, str, int, int]:
        p_id: int = proc
        p_name: str = self.procs[p_id]["proc_name"]
        p_task_id: int = self.procs[p_id]["task_id"]
        p_sc: int = self._procs_status[p_id]
        return p_id, p_name, p_task_id, p_sc

    def set_task_sc_to_proc(self, code: scs, task_id: int | None = None):
        """Dispatches task status code to specified task slot or all active processes."""

        for v in self.procs.values():
            if (v["task_id"] == task_id) or (task_id is None):
                self.set_sc(v["task_id"], code)

    def set_sc(self, id: int, code: scs) -> None:
        """Sets status bitmask for target slot ID."""

        self._procs_status[id] |= code

    def clear_proc_sc(self, code: scs | int, proc_id: int) -> None:
        """Clears status bitmask flags for specified process ID."""

        self._procs_status[proc_id] &= ~(code)

    def proc_is_alive(self, proc_id: int) -> None:
        if (
            self.procs.get(proc_id)
            and not self._sc_sem.get_value()
            and not self.procs[proc_id]["proc"].is_alive()
        ):
            self.logger(
                "Process is dead.",
                LogLevel.CRITICAL,
                self.procs[proc_id]["proc_name"],
            )
            self.close_procs = True

    def kill_procs(self) -> None:
        """Terminates and joins all active worker processes."""

        for v in self.procs.values():
            if v["proc"].is_alive():
                v["proc"].terminate()
                v["proc"].join()

            self.logger(scs.EXIT.label, LogLevel.INFO, v["proc_name"])

    def general_event(self, run: bool, task_ids: list[int]) -> None:
        """Sets or clears general synchronization event across worker tasks."""

        if run:
            self._general_event.set()
        else:
            self._general_event.clear()
            [self.set_sc(task_id, scs.STOP) for task_id in task_ids]

    def get_log(self, proc_id: int) -> list[tuple[int, str]]:
        """Retrieves and decodes log status message for specified process ID."""
        _ = self._log_stream.ring_buf

        logs: list[tuple[int, str]] = []

        while _.rid_buf[proc_id] != _.wid_buf[proc_id]:
            cell: int = _.rid_buf[proc_id]
            need_cell: int = (proc_id * _.cell_amount) + cell
            lrd: int = _.data_header_buf[need_cell]
            start: int = need_cell * _.data_size
            t: int = _.data_buf[start : (start + 8)].cast("q")[0]
            msg: str = f"Log: {
                bytes(_.data_buf[(start + 8) : (start + 8) + lrd]).decode()
            }"
            logs.append((t, msg))
            new_cell: int = cell + 1
            _.rid_buf[proc_id] = new_cell if new_cell < _.cell_amount else 0

        return logs

    def logger(
        self,
        message: str,
        level: LogLevel,
        proc_name: str = "HOST",
        timestamp: int | None = None,
    ) -> None:
        t = timestamp / 1000 if timestamp else time.time()
        log = logger.bind(
            time=datetime.fromtimestamp(t, tz=UTC).strftime(self.time_format),
            level=level.name,
            proc_name=proc_name,
        )
        log.info(message)
