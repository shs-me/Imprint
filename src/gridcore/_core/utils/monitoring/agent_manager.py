import gc
import time
from multiprocessing.synchronize import Semaphore
from typing import Any

from ... import configurations as cfg
from .status_codes import StatusCodes as scs


class AgentManager:
    def __init__(
        self,
        proc_id: int,
        task_id: int,
        segments: dict[str, Any],
        configs: dict[str, Any],
        shm_buf: memoryview,
        sc_sem: Semaphore,
        symbol: str,
        algorithm_module: str,
        algorithm_package: str,
    ) -> None:
        self.proc_id, self.task_id = proc_id, task_id
        self.sc_sem, self.shm_buf = sc_sem, shm_buf
        self.symbol = symbol
        self.algorithm_module = algorithm_module
        self.algorithm_package = algorithm_package

        self.segments_init(segments)
        self.configs_init(configs)
        self.local_segments_init()
        self.task_status = self.status_buf[task_id : task_id + 1]
        self.proc_status = self.status_buf[proc_id : proc_id + 1]

    def configs_init(self, configs: dict[str, Any]) -> None:
        config_subclasses: list[str] = configs.pop("subclasses")
        for name, obj in configs.items():
            if name not in config_subclasses:
                raise ValueError(f"{name} not subclass {cfg.Configuration.__name__}")

            if isinstance(obj, cfg.ConfigurationStrategy):
                self.cfgStrategy = obj
            elif isinstance(obj, cfg.ConfigurationBacktesting):
                self.cfgBacktesting = obj
            elif isinstance(obj, cfg.ConfigurationFootprint):
                self.cfgFootprint = obj
            elif isinstance(obj, cfg.ConfigurationMetrics):
                self.cfgMetrics = obj
            elif isinstance(obj, cfg.ConfigurationRingRawBuf):
                self.cfgRaw = obj
            elif isinstance(obj, cfg.ConfigurationMonitoring):
                self.cfgMonitoring = obj

    def segments_init(self, segments: dict[str, Any]) -> None:
        _slice: slice
        segments_subclasses: list[str] = segments.pop("subclasses")
        for name, _slice in segments.items():
            if name not in segments_subclasses:
                raise ValueError(
                    f"{name} not subclass {cfg.ConfigurationSHMSegments.__name__}"
                )

            if name == cfg.ConfigurationStrategy.__name__:
                self.strategy_buf = self.shm_buf[_slice]
            elif name == cfg.ConfigurationFootprint.__name__:
                self.footprint_buf = self.shm_buf[_slice]
            elif name == cfg.ConfigurationMetrics.__name__:
                self.metrics_buf = self.shm_buf[_slice]
            elif name == cfg.ConfigurationRingRawBuf.__name__:
                self.raw_buf = self.shm_buf[_slice]
            elif name == cfg.ConfigurationMonitoring.__name__:
                self.monitoring_buf = self.shm_buf[_slice]

    def local_segments_init(self) -> None:
        self.status_buf = self.monitoring_buf[
            slice(*self.cfgMonitoring.procs_buf)
        ].cast("q")

    def check_base_task(self, complete: bool) -> bool | int:
        if self.task_status[0] != 0 or self.proc_status[0] != 0:
            while self.task_status[0] == 0:
                time.sleep(0.001)

            task_sc: int = self.task_status[0]
            _return_data, _clear_task, _set_proc_sc = task_sc, True, None
            if task_sc & scs.EXIT:
                _return_data, _set_proc_sc = True, task_sc

            elif task_sc & scs.COMPLETE:
                _return_data, _clear_task = (
                    (True, False) if complete else (False, False)
                )

            elif task_sc & scs.GC_COLLECT:
                gc.collect()
                _return_data = False

            elif task_sc & scs.RUN:
                _return_data = False

            if _clear_task:
                self.clear_task_sc(task_sc)
            if _set_proc_sc:
                self.set_proc_sc(_set_proc_sc)

            return _return_data

        else:
            return False

    def set_proc_sc(self, code: scs | int) -> None:
        self.proc_status[0] |= code
        self.sc_sem.release()

    def set_task_sc(self, code: scs | int) -> None:
        self.task_status[0] |= code

    def clear_task_sc(self, code: scs | int) -> None:
        self.task_status[0] &= ~(code)

    def _for_error_action(self) -> None:
        self.proc_status[0] |= scs.ERROR
        self.sc_sem.release()
