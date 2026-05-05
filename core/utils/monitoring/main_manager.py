from datetime import date
from multiprocessing.synchronize import Event, Semaphore
from typing import Any

from loguru import logger

from core import configurations as cfg
from core.utils.monitoring.status_codes import StatusCodes as scs


class MainManager:
    def __init__(
        self,
        segments: dict[str, Any],
        configs: dict[str, Any],
        shm_buf: memoryview,
    ) -> None:
        self.shm_buf: memoryview = shm_buf
        self.startDate: date = date.today()
        self.segments_init(segments)
        self.configs_init(configs)
        self.local_segments_init()

    def configs_init(self, configs: dict[str, Any]) -> None:
        config_subclasses: list[str] = configs["subclasses"]
        for name, obj in configs.items():
            if isinstance(obj, list):
                continue

            if name not in config_subclasses:
                raise ValueError(f"{name} not subclass {cfg.Configuration.__name__}")

            if isinstance(obj, cfg.ConfigurationMonitoring):
                self.cfgMonitoring = obj

            elif isinstance(obj, cfg.ConfigurationMetrics):
                self.cfgMetrics = obj

            elif isinstance(obj, cfg.ConfigurationBacktesting):
                self.cfgBacktesting = obj

    def segments_init(self, segments: dict[str, Any]) -> None:
        _slice: slice
        segments_subclasses: list[str] = segments["subclasses"]
        for name, _slice in segments.items():
            if isinstance(_slice, list):
                continue

            if name not in segments_subclasses:
                raise ValueError(
                    f"{name} not subclass {cfg.ConfigurationSHMSegments.__name__}"
                )

            if name == cfg.ConfigurationMonitoring.__name__:
                self.monitoring_buf = self.shm_buf[_slice]

            elif name == cfg.ConfigurationMetrics.__name__:
                self.metrics_buf = self.shm_buf[_slice]

    def local_segments_init(self) -> None:
        self.procs_buf = self.monitoring_buf[slice(*self.cfgMonitoring.procs_buf)].cast(
            "q"
        )

    def run(
        self,
        procs: dict[int, dict],
        general_event: Event,
        scs_sem: Semaphore,
    ) -> None:
        self.procs = procs
        self.scs_sem = scs_sem
        self.sleep_all = general_event
        # - - -
        self.sleep_all.set()
        print(self.procs)
        while True:
            scs_sem.acquire(timeout=60)
            if date.today() > self.startDate:
                self.set_task_sc_to_procs(scs.GC_COLLECT)

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
        procs, procs_buf = self.procs, self.procs_buf
        for _ in range(len(self.procs)):
            for k, v in procs.items():
                sc = procs_buf[k]
                # Action's
                # General
                if sc & scs.ERROR:
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

                elif sc & scs.FP_IDX_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.FP_IDX_FILLED.label}")
                    for task_id in self.get_procs_task_id(["LOGIC", "PARSING"]):
                        self.set_task_sc_to_proc(scs.FP_RE_INIT, task_id)

                elif sc & scs.FP_IDY_FILLED:
                    logger.warning(f"{v['proc_name']} | {scs.FP_IDY_FILLED.label}")
                    for task_id in self.get_procs_task_id(["LOGIC", "PARSING"]):
                        self.set_task_sc_to_proc(scs.FP_RE_INIT, task_id)

                elif sc & scs.FP_RE_INIT:
                    logger.success(f"{v['proc_name']} | {scs.FP_RE_INIT.label}")
                    self.set_task_sc_to_procs(scs.RUN)

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
        self.procs_buf[task_id] |= code

    def set_task_sc_to_procs(self, code: scs):
        for _, data in self.procs.items():
            self.procs_buf[data["task_id"]] |= code

    def clear_proc_sc(self, code: scs | int, proc_id: int) -> None:
        self.procs_buf[proc_id] &= ~(code)

    def get_procs_task_id(self, procs_name: list[str]) -> list[int]:
        return [
            v["task_id"] for k, v in self.procs.items() if v["proc_name"] in procs_name
        ]
