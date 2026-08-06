"""Main process manager tracking worker process health and orchestrating tasks."""

from datetime import date

from loguru import logger

from ...settings import DataStreamProc, ExecutionProc, LogicProc, ParsingProc, ProcsData
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
        self.close_procs: bool = False
        self.close_core: bool = False

    def get_text(self, proc_id: int) -> str:
        """Retrieves and decodes text status message for specified process ID."""
        text: str = f"{self.procs[proc_id]['proc_name']}: "

        cell: int = self._ts_rid[proc_id]
        need_cell: int = (proc_id * self._ts_cell_amount) + cell
        lrd: int = self._ts_data_header[need_cell]
        start: int = need_cell * self._ts_data_size
        text = text + bytes(self._ts_data[start : start + lrd]).decode()
        new_cell: int = cell + 1
        self._ts_rid[proc_id] = new_cell if new_cell < self._ts_cell_amount else 0

        return text

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
                self._sc_sem.acquire(timeout=60)

                if date.today() > self.startDate:
                    self.set_task_sc_to_proc(scs.GC_COLLECT)
                    self.startDate = date.today()

                if bool(len(procs)):
                    if self.procs_is_alive():
                        self.check_process_status_code()
                        if not self.close_core:
                            continue
            return

    def procs_is_alive(self) -> bool:
        """Validates that all registered worker processes are active.

        Returns:
            bool: True if all processes are running.
        """

        for k, v in self.procs.items():
            if v["proc"].is_alive() is False:
                logger.critical(f"Process {v['proc_name']} is dead.")
                return False

        return True

    def check_process_status_code(self) -> None:

        if self._main_status[self.market_data_wss]:
            self.check_data_stream_proc()
            self._main_status[self.market_data_wss] = 0

        if self._main_status[self.parsing]:
            self.check_parsing_proc()
            self._main_status[self.parsing] = 0

        if self._main_status[self.logic]:
            self.check_logic_proc()
            self._main_status[self.logic] = 0

        if self._main_status[self.execution]:
            self.check_execution_proc()
            self._main_status[self.execution] = 0

        if self.close_procs:
            self.kill_procs()
            self.close_core = True

    def check_data_stream_proc(self) -> None:
        p_id, p_name, p_task_id, sc = self.get_proc_data(self.market_data_wss)

        if self.action_for_base_sc(sc, p_id, p_name):
            pass

        elif sc & scs.DATA_PREPPERED:
            logger.warning(f"{p_name} | {scs.DATA_PREPPERED.label}")
            self.set_task_sc_to_proc(scs.COMPLETE)

        elif sc & scs.BIG_RAW_DATA:
            logger.warning(f"{p_name} | {scs.BIG_RAW_DATA.label}")
            self.close_procs = True

        if sc != 0:
            self.clear_proc_sc(code=sc, proc_id=p_id)

    def check_parsing_proc(self) -> None:
        p_id, p_name, p_task_id, sc = self.get_proc_data(self.parsing)

        if self.action_for_base_sc(sc, p_id, p_name):
            pass

        elif sc & scs.UNVALID_DATA:
            logger.warning(f"{p_name} | {scs.UNVALID_DATA.label}")
            self.close_procs = True

        elif sc & scs.FP_IDX_FILLED:
            logger.warning(f"{p_name} | {scs.FP_IDX_FILLED.label}")
            self.set_task_sc_to_proc(scs.FP_RE_INIT, p_task_id)
            self.set_task_sc_to_proc(scs.FP_RE_INIT, self.procs[self.logic]["task_id"])

        elif sc & scs.FP_IDY_FILLED:
            logger.warning(f"{p_name} | {scs.FP_IDY_FILLED.label}")
            self.close_procs = True

        elif sc & scs.FP_RE_INIT:
            logger.success(f"{p_name} | {scs.FP_RE_INIT.label}")
            self.set_task_sc_to_proc(scs.RUN, p_task_id)

        if sc != 0:
            self.clear_proc_sc(code=sc, proc_id=p_id)

    def check_logic_proc(self) -> None:
        p_id, p_name, p_task_id, sc = self.get_proc_data(self.logic)

        if self.action_for_base_sc(sc, p_id, p_name):
            pass

        elif sc & scs.ANALYSIS_LAG_MORE_SAFE_LAG:
            logger.warning(f"{p_name} | {scs.ANALYSIS_LAG_MORE_SAFE_LAG.label}")
            self.set_task_sc_to_proc(scs.RUN, p_task_id)

        if sc != 0:
            self.clear_proc_sc(code=sc, proc_id=p_id)

    def check_execution_proc(self) -> None:
        p_id, p_name, p_task_id, sc = self.get_proc_data(self.execution)

        if self.action_for_base_sc(sc, p_id, p_name):
            pass

        elif sc & scs.LOSS_MORE_LIMIT:
            logger.warning(f"{p_name} | {scs.LOSS_MORE_LIMIT.label}")
            self.close_procs = True

        elif sc & scs.QTY_LESS_LIMIT:
            logger.warning(f"{p_name} | {scs.QTY_LESS_LIMIT.label}")
            self.close_procs = True

        elif sc & scs.ORDER_LIMIT:
            logger.warning(f"{p_name} | {scs.QTY_LESS_LIMIT.label}")
            self.close_procs = True

        if sc != 0:
            self.clear_proc_sc(code=sc, proc_id=p_id)

    def action_for_base_sc(self, sc: int, proc_id: int, proc_name: str) -> bool:
        if sc & scs.ERROR:
            logger.error(f"{proc_name}: {scs.ERROR.label}")
            self.close_procs = True

        elif sc & scs.COMPLETE:
            logger.success(f"{proc_name} | {scs.COMPLETE.label}")
            self.procs.pop(proc_id)

        elif sc & scs.HAVE_TEXT:
            text = self.get_text(proc_id)
            print(text, flush=True)

        elif sc & scs.RING_BUFFER_TEXT_STREAM_OVERFLOW:
            logger.warning(
                f"{proc_name} | {scs.RING_BUFFER_TEXT_STREAM_OVERFLOW.label}"
            )

        else:
            return False

        return True

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

    def kill_procs(self) -> None:
        """Terminates and joins all active worker processes."""

        for _, v in self.procs.items():
            if v["proc"].is_alive():
                v["proc"].terminate()
                v["proc"].join()

            logger.warning(f"{v['proc_name']} | {scs.EXIT.label}")

    def general_event(self, run: bool, task_ids: list[int]) -> None:
        """Sets or clears general synchronization event across worker tasks."""

        if run:
            self._general_event.set()
        else:
            self._general_event.clear()
            [self.set_sc(task_id, scs.STOP) for task_id in task_ids]
