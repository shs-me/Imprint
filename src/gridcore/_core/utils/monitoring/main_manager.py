"""Main process manager tracking worker process health and orchestrating tasks."""

from datetime import date

from loguru import logger

from ...settings import ProcsData
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
        self.status_buf: memoryview = self.cfgMetrics.status.cast("q")

    def get_text(self, proc_id: int) -> str:
        """Retrieves and decodes text status message for specified process ID."""

        text_buf: memoryview = self.cfgMetrics.text
        start = proc_id * self.cfgMetrics.text_size
        len_t, start = text_buf[start : start + 8].cast("q")[0], start + 8
        text: str = f"{self.procs[proc_id]['proc_name']}: "
        if len_t > 0:
            text = text + bytes(text_buf[start : start + len_t]).decode()

        return text

    def run(self, procs: dict[int, ProcsData]) -> None:
        """Primary supervisor loop waiting on process semaphores and handling status code events."""

        self.procs: dict[int, ProcsData] = procs
        # - - -
        while True:
            if bool(len(procs)):
                self._sc_sem.acquire(timeout=60)

                if date.today() > self.startDate:
                    self.set_task_sc_to_proc(scs.GC_COLLECT)
                    self.startDate = date.today()

                if bool(len(procs)):
                    if self.procs_is_alive():
                        if self.check_process_status_code():
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

    def check_process_status_code(self) -> bool:
        """Evaluates active process status flags and executes control actions (re-init, error, shutdown).

        Returns:
            bool: True if monitoring loop should continue processing.
        """

        procs, status_buf = self.procs, self.status_buf
        for _ in range(len(self.procs)):
            for k, v in procs.items():
                close_procs, return_false = False, False
                sc = status_buf[k]
                # Action's
                # General
                if sc == 0:
                    continue

                elif sc & scs.ERROR:
                    logger.error(f"{v['proc_name']}: {scs.ERROR.label}")
                    close_procs, return_false = True, True

                elif sc & scs.COMPLETE:
                    logger.success(f"{v['proc_name']} | {scs.COMPLETE.label}")
                    print(self.get_text(k), flush=True)
                    procs.pop(k)
                    break

                # Parsing
                elif sc & scs.UNVALID_DATA:
                    logger.warning(f"{v['proc_name']} | {scs.UNVALID_DATA.label}")
                    close_procs, return_false = True, True

                elif sc & scs.FP_IDX_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.FP_IDX_FILLED.label}")
                    for task_id in self.get_proc_task_id(["LOGIC", "PARSING"]):
                        self.set_task_sc_to_proc(scs.FP_RE_INIT, task_id)

                elif sc & scs.FP_IDY_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.FP_IDY_FILLED.label}")
                    close_procs, return_false = True, True

                elif sc & scs.FP_RE_INIT:
                    logger.success(f"{v['proc_name']} | {scs.FP_RE_INIT.label}")
                    self.set_task_sc_to_proc(scs.RUN, v["task_id"])

                # Logic
                elif sc & scs.ANALYSIS_LAG_MORE_SAFE_LAG:
                    logger.warning(
                        f"{v['proc_name']} | {scs.ANALYSIS_LAG_MORE_SAFE_LAG.label}"
                    )
                    self.set_task_sc_to_proc(scs.RUN, v["task_id"])

                # Network/Sim
                elif sc & scs.DATA_PREPPERED:
                    logger.warning(f"{v['proc_name']} | {scs.DATA_PREPPERED.label}")
                    self.set_task_sc_to_proc(scs.COMPLETE)

                elif sc & scs.BIG_RAW_DATA:
                    logger.warning(f"{v['proc_name']} | {scs.BIG_RAW_DATA.label}")
                    close_procs, return_false = True, True

                # Execution
                elif sc & scs.LOSS_MORE_LIMIT:
                    logger.warning(f"{v['proc_name']} | {scs.LOSS_MORE_LIMIT.label}")
                    close_procs, return_false = True, True

                elif sc & scs.QTY_LESS_LIMIT:
                    logger.warning(f"{v['proc_name']} | {scs.QTY_LESS_LIMIT.label}")
                    close_procs, return_false = True, True

                if sc != 0:
                    self.clear_proc_sc(code=sc, proc_id=k)
                if close_procs:
                    self.kill_procs()
                if return_false:
                    return False
        return True

    def clear_proc_sc(self, code: scs | int, proc_id: int) -> None:
        """Clears status bitmask flags for specified process ID."""

        self.status_buf[proc_id] &= ~(code)

    def set_task_sc_to_proc(self, code: scs, task_id: int | None = None):
        """Dispatches task status code to specified task slot or all active processes."""

        for p, _ in self.procs.items():
            if (_["task_id"] == task_id) or (task_id is None):
                self.set_sc(_["task_id"], code)

    def set_sc(self, id: int, code: scs) -> None:
        """Sets status bitmask for target slot ID."""

        self.status_buf[id] |= code

    def get_proc_task_id(self, procs_name: list[str]) -> list[int]:
        """Resolves task IDs associated with specified process name keywords."""

        return [
            v["task_id"]
            for k, v in self.procs.items()
            for p in procs_name
            if p in v["proc_name"]
        ]

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
