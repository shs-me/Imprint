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
    ) -> None:
        self.proc_id, self.task_id = proc_id, task_id
        self.sc_sem, self.shm_buf = sc_sem, shm_buf
        self.symbol: str = symbol

        self.segments_init(segments)
        self.configs_init(configs)

        self.task_status: memoryview = self.cfgMetrics.status.cast("q")[
            task_id : task_id + 1
        ]
        self.proc_status: memoryview = self.cfgMetrics.status.cast("q")[
            proc_id : proc_id + 1
        ]

    def segments_init(self, segments: dict[str, Any]) -> None:
        _slice: slice
        segments_subclasses: list[str] = segments.pop("subclasses")
        for name, _slice in segments.items():
            if name not in segments_subclasses:
                raise ValueError(f"{name} not subclass {cfg.cfgSHMSegments.__name__}")

            elif name == cfg.cfgStrategy.__name__:
                self.strategy_buf = self.shm_buf[_slice]
            elif name == cfg.cfgFootprint.__name__:
                self.footprint_buf = self.shm_buf[_slice]
            elif name == cfg.cfgMetrics.__name__:
                self.metrics_buf = self.shm_buf[_slice]
            elif name == cfg.cfgWssRingBuf.__name__:
                self.raw_buf = self.shm_buf[_slice]

    def configs_init(self, configs: dict[str, Any]) -> None:
        config_subclasses: list[str] = configs.pop("subclasses")
        for name, obj in configs.items():
            if name not in config_subclasses:
                raise ValueError(f"{name} not subclass {cfg.Configuration.__name__}")

            elif isinstance(obj, cfg.cfgBacktesting):
                self.cfgBacktesting = obj
            elif isinstance(obj, cfg.cfgStrategy):
                self.cfgStrategy = obj
                self.bind_shm_segments(self.cfgStrategy, self.strategy_buf)
            elif isinstance(obj, cfg.cfgFootprint):
                self.cfgFootprint = obj
                self.bind_shm_segments(self.cfgFootprint, self.footprint_buf)
            elif isinstance(obj, cfg.cfgMetrics):
                self.cfgMetrics = obj
                self.bind_shm_segments(self.cfgMetrics, self.metrics_buf)
            elif isinstance(obj, cfg.cfgWssRingBuf):
                self.cfgRaw = obj
                self.bind_shm_segments(self.cfgRaw, self.raw_buf)

    def bind_shm_segments(self, cfg_obj: object, shm_buf: memoryview) -> None:
        for attr_name in list(cfg_obj.__dict__.keys()):
            attr_val = getattr(cfg_obj, attr_name)
            if isinstance(attr_val, tuple):
                if len(attr_val) == 2:
                    setattr(cfg_obj, attr_name, shm_buf[slice(*attr_val)])

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
