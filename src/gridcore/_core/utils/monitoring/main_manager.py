from datetime import date
from multiprocessing.synchronize import Semaphore
from typing import Any

from loguru import logger

from ... import configurations as cfg
from .status_codes import StatusCodes as scs


class MainManager:
    def __init__(
        self, segments: dict[str, Any], configs: dict[str, Any], shm_buf: memoryview
    ) -> None:
        self.shm_buf: memoryview = shm_buf
        self.startDate: date = date.today()
        self.segments_init(segments)
        self.configs_init(configs)
        self.status_buf: memoryview = self.cfgMetrics.status.cast("q")

    def segments_init(self, segments: dict[str, Any]) -> None:
        _slice: slice
        segments_subclasses: list[str] = segments["subclasses"]
        for name, _slice in segments.items():
            if isinstance(_slice, list):
                continue
            if name not in segments_subclasses:
                raise ValueError(f"{name} not subclass {cfg.cfgSHMSegments.__name__}")
            elif name == cfg.cfgMetrics.__name__:
                self.metrics_buf = self.shm_buf[_slice]

    def configs_init(self, configs: dict[str, Any]) -> None:
        config_subclasses: list[str] = configs["subclasses"]
        for name, obj in configs.items():
            if isinstance(obj, list):
                continue
            if name not in config_subclasses:
                raise ValueError(f"{name} not subclass {cfg.Configuration.__name__}")
            elif isinstance(obj, cfg.cfgBacktesting):
                self.cfgBacktesting = obj
            elif isinstance(obj, cfg.cfgMetrics):
                self.cfgMetrics = obj
                self.bind_shm_segments(self.cfgMetrics, self.metrics_buf)

    def bind_shm_segments(self, cfg_obj: object, shm_buf: memoryview) -> None:
        for attr_name in list(cfg_obj.__dict__.keys()):
            attr_val = getattr(cfg_obj, attr_name)
            if isinstance(attr_val, tuple):
                if len(attr_val) == 2:
                    setattr(cfg_obj, attr_name, shm_buf[slice(*attr_val)])

    def run(self, procs: dict[int, dict], scs_sem: Semaphore) -> None:
        self.procs = procs
        self.scs_sem = scs_sem
        # - - -
        while True:
            if bool(len(procs)):
                scs_sem.acquire(timeout=60)
                if date.today() > self.startDate:
                    self.set_task_sc_to_procs(scs.GC_COLLECT)
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
                    procs.pop(k)
                    break

                # Parsing
                elif sc & scs.UNVALID_DATA:
                    logger.warning(f"{v['proc_name']} | {scs.UNVALID_DATA.label}")
                    self.set_task_sc_to_procs(scs.EXIT)

                elif sc & scs.BUF_DFM_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.BUF_DFM_FILLED.label}")
                    self.set_task_sc_to_procs(scs.EXIT)

                elif sc & scs.FP_IDX_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.FP_IDX_FILLED.label}")
                    for task_id in self.get_procs_task_id(["LOGIC", "PARSING"]):
                        self.set_task_sc_to_proc(scs.FP_RE_INIT, task_id)

                elif sc & scs.FP_IDY_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.FP_IDY_FILLED.label}")
                    self.set_task_sc_to_procs(scs.EXIT)

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
                    self.set_task_sc_to_procs(scs.COMPLETE)

                elif sc & scs.BIG_RAW_DATA:
                    logger.warning(f"{v['proc_name']} | {scs.BIG_RAW_DATA.label}")
                    self.set_task_sc_to_procs(scs.EXIT)

                # Execution
                elif sc & scs.LOSS_MORE_LIMIT:
                    logger.warning(f"{v['proc_name']} | {scs.LOSS_MORE_LIMIT.label}")
                    self.set_task_sc_to_procs(scs.EXIT)

                elif sc & scs.QTY_LESS_LIMIT:
                    logger.warning(f"{v['proc_name']} | {scs.QTY_LESS_LIMIT.label}")
                    self.set_task_sc_to_procs(scs.EXIT)

                if sc != 0:
                    self.clear_proc_sc(code=sc, proc_id=k)

        return True

    def set_task_sc_to_proc(self, code: scs, task_id: int):
        self.status_buf[task_id] |= code

    def set_task_sc_to_procs(self, code: scs):
        for _, data in self.procs.items():
            self.status_buf[data["task_id"]] |= code

    def clear_proc_sc(self, code: scs | int, proc_id: int) -> None:
        self.status_buf[proc_id] &= ~(code)

    def get_procs_task_id(self, procs_name: list[str]) -> list[int]:
        return [
            v["task_id"]
            for k, v in self.procs.items()
            for p in procs_name
            if p in v["proc_name"]
        ]
