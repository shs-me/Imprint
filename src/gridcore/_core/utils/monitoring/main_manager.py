import ctypes
import os
import signal
import sys
from datetime import date
from multiprocessing.synchronize import Semaphore

from loguru import logger

from .base_manager import Manager
from .status_codes import StatusCodes as scs


class MainManager(Manager):
    def __init__(
        self,
        segments: dict[str, slice],
        shm_buf: memoryview,
        configs: list,
    ) -> None:
        super().__init__(segments, shm_buf, configs)

        self.startDate: date = date.today()
        self.status_buf: memoryview = self.cfgMetrics.status.cast("q")

    def get_text(self, proc_id: int) -> str:
        text_buf: memoryview = self.cfgMetrics.text
        start = proc_id * self.cfgMetrics.text_size
        len_t, start = text_buf[start : start + 8].cast("q")[0], start + 8
        text: str = f"{self.procs[proc_id]['proc_name']}: "
        if len_t > 0:
            text = text + bytes(text_buf[start : start + len_t]).decode()

        return text

    def run(self, procs: dict[int, dict], scs_sem: Semaphore) -> None:
        self.procs = procs
        self.scs_sem = scs_sem
        # - - -
        while True:
            if bool(len(procs)):
                scs_sem.acquire(timeout=60)
                if date.today() > self.startDate:
                    self.set_task_sc_to_proc(scs.GC_COLLECT)
                    self.startDate = date.today()

                if bool(len(procs)):
                    if self.procs_is_alive():
                        if self.check_process_status_code():
                            continue

            return

    def procs_is_alive(self) -> bool:
        for k, v in self.procs.items():
            if v["proc"].is_alive() is False:
                logger.critical(f"Process {v['proc_name']} is dead.")
                return False

        return True

    def check_process_status_code(self) -> bool:
        procs, status_buf = self.procs, self.status_buf
        for _ in range(len(self.procs)):
            for k, v in procs.items():
                sc = status_buf[k]
                # Action's
                # General
                if sc == 0:
                    continue

                elif sc & scs.ERROR:
                    logger.error(f"{v['proc_name']}: {scs.ERROR.label}")
                    return False

                elif sc & scs.EXIT:
                    logger.warning(f"{v['proc_name']} | {scs.EXIT.label}")
                    procs.pop(k)
                    break

                elif sc & scs.COMPLETE:
                    logger.success(f"{v['proc_name']} | {scs.COMPLETE.label}")
                    print(self.get_text(k), flush=True)
                    procs.pop(k)
                    break

                # Parsing
                elif sc & scs.UNVALID_DATA:
                    logger.warning(f"{v['proc_name']} | {scs.UNVALID_DATA.label}")
                    self.set_task_sc_to_proc(scs.EXIT)

                elif sc & scs.FP_IDX_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.FP_IDX_FILLED.label}")
                    for task_id in self.get_proc_task_id(["LOGIC", "PARSING"]):
                        self.set_task_sc_to_proc(scs.FP_RE_INIT, task_id)

                elif sc & scs.FP_IDY_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.FP_IDY_FILLED.label}")
                    self.set_task_sc_to_proc(scs.EXIT)

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
                    self.set_task_sc_to_proc(scs.EXIT)

                # Execution
                elif sc & scs.LOSS_MORE_LIMIT:
                    logger.warning(f"{v['proc_name']} | {scs.LOSS_MORE_LIMIT.label}")
                    self.set_task_sc_to_proc(scs.EXIT)

                elif sc & scs.QTY_LESS_LIMIT:
                    logger.warning(f"{v['proc_name']} | {scs.QTY_LESS_LIMIT.label}")
                    self.set_task_sc_to_proc(scs.EXIT)

                if sc != 0:
                    self.clear_proc_sc(code=sc, proc_id=k)

        return True

    def clear_proc_sc(self, code: scs | int, proc_id: int) -> None:
        self.status_buf[proc_id] &= ~(code)

    def set_task_sc_to_proc(self, code: scs, task_id: int | None = None):
        if code & scs.EXIT:
            pids = []
            for _, v in self.procs.items():
                if (v["task_id"] == task_id) or (task_id is None):
                    pids.append(v["proc"].pid)
                    logger.warning(f"{v['proc_name']} | {scs.EXIT.label}")

            generate_ctrl_c_event(pids)
        else:
            [
                self.set_sc(_["task_id"], code)
                for p, _ in self.procs.items()
                if (_["task_id"] == task_id) or (task_id is None)
            ]

    def set_sc(self, id: int, code: scs) -> None:
        self.status_buf[id] |= code

    def get_proc_task_id(self, procs_name: list[str]) -> list[int]:
        return [
            v["task_id"]
            for k, v in self.procs.items()
            for p in procs_name
            if p in v["proc_name"]
        ]


def generate_ctrl_c_event(pids: list[int]) -> None:
    if sys.platform == "win32":
        [ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, pid) for pid in pids]
    elif sys.platform == "linux":
        [os.kill(pid, signal.SIGINT) for pid in pids]
