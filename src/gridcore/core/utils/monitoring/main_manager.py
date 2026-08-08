"""Main process manager tracking worker process health and orchestrating tasks."""

import time
from datetime import date, datetime

from loguru import logger

from ...settings import (
    DataStreamProc,
    ExecutionProc,
    LogicProc,
    LogLevel,
    ParsingProc,
    ProcsData,
)
from ...settings import StatusCodes as scs
from .base_manager import Manager


class MainManager(Manager):
    """Central status manager monitoring worker process health and handling process status codes."""

    def __init__(
        self,
        segments: dict[str, slice],
        shm_buf: memoryview,
        configs: list,
        main_tools: list,
    ) -> None:
        super().__init__(segments, shm_buf, configs, main_tools)

        self.startDate: date = date.today()
        self.time_format: str = (
            "%H:%M:%S.%f" if self.cfgSetup.backtesting else "%Y:%m:%d-%H:%M:%S.%f"
        )
        self.close_procs: bool = False
        self.close_core: bool = False

    def run(
        self,
        procs: dict[int, ProcsData],
        market_data_wss: DataStreamProc,
        parsing: ParsingProc,
        logic: LogicProc,
        execution: ExecutionProc,
    ) -> None:
        """Primary supervisor loop waiting on process semaphores and handling status code events."""

        self.procs: dict[int, ProcsData] = procs
        self.market_data_wss: DataStreamProc = market_data_wss
        self.parsing: ParsingProc = parsing
        self.logic: LogicProc = logic
        self.execution: ExecutionProc = execution
        # - - -
        while True:
            if bool(len(procs)):
                self._sc_sem.acquire(timeout=30)

                if date.today() > self.startDate:
                    self.set_task_sc_to_proc(scs.GC_COLLECT)
                    self.startDate = date.today()

                self.check_process_status_code()
                if not self.close_core:
                    continue
            return

    def check_process_status_code(self) -> None:
        if self._main_status[self.market_data_wss]:
            self.check_data_stream_proc()
            self._main_status[self.market_data_wss] -= 1

        if self._main_status[self.parsing]:
            self.check_parsing_proc()
            self._main_status[self.parsing] -= 1

        if self._main_status[self.logic]:
            self.check_logic_proc()
            self._main_status[self.logic] -= 1

        if self._main_status[self.execution]:
            self.check_execution_proc()
            self._main_status[self.execution] -= 1

        if self.close_procs:
            self.kill_procs()
            self.close_core = True

    def check_data_stream_proc(self) -> None:
        if not self.procs.get(self.market_data_wss):
            return

        p_id, p_name, p_task_id, sc = self.get_proc_data(self.market_data_wss)

        self.action_for_base_sc(sc, p_id, p_name)

        if sc & scs.DATA_PREPPERED:
            self.logger(scs.DATA_PREPPERED.label, LogLevel.WARNING, p_name)
            self.set_task_sc_to_proc(scs.COMPLETE)
            self.clear_proc_sc(scs.DATA_PREPPERED, p_id)

        if sc & scs.BIG_RAW_DATA:
            self.logger(scs.BIG_RAW_DATA.label, LogLevel.WARNING, p_name)
            self.close_procs = True
            self.clear_proc_sc(scs.BIG_RAW_DATA, p_id)

        self.proc_is_alive(p_id)

    def check_parsing_proc(self) -> None:
        if not self.procs.get(self.parsing):
            return

        p_id, p_name, p_task_id, sc = self.get_proc_data(self.parsing)

        self.action_for_base_sc(sc, p_id, p_name)

        if sc & scs.UNVALID_DATA:
            self.logger(scs.UNVALID_DATA.label, LogLevel.WARNING, p_name)
            self.close_procs = True
            self.clear_proc_sc(scs.UNVALID_DATA, p_id)

        if sc & scs.FP_IDX_FILLED:
            self.logger(scs.FP_IDX_FILLED.label, LogLevel.WARNING, p_name)
            self.set_task_sc_to_proc(scs.FP_RE_INIT, p_task_id)
            self.set_task_sc_to_proc(scs.FP_RE_INIT, self.procs[self.logic]["task_id"])
            self.clear_proc_sc(scs.FP_IDX_FILLED, p_id)

        if sc & scs.FP_IDY_FILLED:
            self.logger(scs.FP_IDY_FILLED.label, LogLevel.WARNING, p_name)
            self.close_procs = True
            self.clear_proc_sc(scs.FP_IDY_FILLED, p_id)

        if sc & scs.FP_RE_INIT:
            self.logger(scs.FP_RE_INIT.label, LogLevel.SUCCESS, p_name)
            self.set_task_sc_to_proc(scs.RUN, p_task_id)
            self.clear_proc_sc(scs.FP_RE_INIT, p_id)

        self.proc_is_alive(p_id)

    def check_logic_proc(self) -> None:
        if not self.procs.get(self.logic):
            return

        p_id, p_name, p_task_id, sc = self.get_proc_data(self.logic)

        self.action_for_base_sc(sc, p_id, p_name)

        if sc & scs.ANALYSIS_LAG_MORE_SAFE_LAG:
            self.logger(scs.ANALYSIS_LAG_MORE_SAFE_LAG.label, LogLevel.WARNING, p_name)
            self.set_task_sc_to_proc(scs.RUN, p_task_id)
            self.clear_proc_sc(scs.ANALYSIS_LAG_MORE_SAFE_LAG, p_id)

        self.proc_is_alive(p_id)

    def check_execution_proc(self) -> None:
        if not self.procs.get(self.execution):
            return

        p_id, p_name, p_task_id, sc = self.get_proc_data(self.execution)

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
        if sc & scs.HAVE_TEXT:
            logs: list[tuple[int, str]] = self.get_text(proc_id)
            for timestamp, log in logs:
                self.logger(log, LogLevel.INFO, proc_name, timestamp)

            self.clear_proc_sc(scs.HAVE_TEXT, proc_id)

        if sc & scs.ERROR:
            self.logger(scs.ERROR.label, LogLevel.ERROR, proc_name)
            self.close_procs = True
            self.clear_proc_sc(scs.ERROR, proc_id)

        if sc & scs.COMPLETE:
            self.logger(scs.COMPLETE.label, LogLevel.WARNING, proc_name)
            self.procs.pop(proc_id)
            self.clear_proc_sc(scs.COMPLETE, proc_id)

        if sc & scs.RING_BUFFER_TEXT_STREAM_OVERFLOW:
            self.logger(
                scs.RING_BUFFER_TEXT_STREAM_OVERFLOW.label, LogLevel.WARNING, proc_name
            )
            self.clear_proc_sc(scs.RING_BUFFER_TEXT_STREAM_OVERFLOW, proc_id)

    def get_proc_data(self, proc: int) -> tuple[int, str, int, int]:
        p_id = proc
        p_name = self.procs[p_id]["proc_name"]
        p_task_id = self.procs[p_id]["task_id"]
        p_sc = self._procs_status[p_id]
        return p_id, p_name, p_task_id, p_sc

    def set_task_sc_to_proc(self, code: scs, task_id: int | None = None):
        """Dispatches task status code to specified task slot or all active processes."""

        for p, _ in self.procs.items():
            if (_["task_id"] == task_id) or (task_id is None):
                self.set_sc(_["task_id"], code)

    def set_sc(self, id: int, code: scs) -> None:
        """Sets status bitmask for target slot ID."""

        self._procs_status[id] |= code

    def clear_proc_sc(self, code: scs | int, proc_id: int) -> None:
        """Clears status bitmask flags for specified process ID."""

        self._procs_status[proc_id] &= ~(code)

    def proc_is_alive(self, proc_id: int) -> None:
        if self.procs.get(proc_id) and not self._sc_sem.get_value():
            if not self.procs[proc_id]["proc"].is_alive():
                self.logger(
                    "Process is dead.",
                    LogLevel.CRITICAL,
                    self.procs[proc_id]["proc_name"],
                )
                self.close_procs = True

    def kill_procs(self) -> None:
        """Terminates and joins all active worker processes."""

        for _, v in self.procs.items():
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

    def get_text(self, proc_id: int) -> list[tuple[int, str]]:
        """Retrieves and decodes text status message for specified process ID."""
        logs: list[tuple[int, str]] = []

        while self._ts_rid[proc_id] != self._ts_wid[proc_id]:
            cell: int = self._ts_rid[proc_id]
            need_cell: int = (proc_id * self._ts_cell_amount) + cell
            lrd: int = self._ts_data_header[need_cell]
            start: int = need_cell * self._ts_data_size
            t = self._ts_data[start : (start + 8)].cast("q")[0]
            msg = bytes(self._ts_data[(start + 8) : (start + 8) + lrd]).decode()
            logs.append((t, msg))
            new_cell: int = cell + 1
            self._ts_rid[proc_id] = new_cell if new_cell < self._ts_cell_amount else 0

        return logs

    def logger(
        self,
        message: str,
        level: LogLevel,
        proc_name: str = "Main",
        timestamp: int | None = None,
    ) -> None:
        t = timestamp / 1000 if timestamp else time.time()
        log = logger.bind(
            time=datetime.fromtimestamp(t).strftime(self.time_format),
            level=level.name,
            proc_name=proc_name,
        )
        log.info(message)
