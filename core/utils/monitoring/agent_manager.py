from multiprocessing.synchronize import Semaphore
from typing import Any

import numpy as np

from ... import configurations as cfg
from . import StatusCodes as sc


class AgentManager:
    def __init__(
        self,
        proc_id: int,
        task_id: int,
        segments: dict[str, Any],
        configs: dict[str, Any],
        shm_buf: memoryview,
        sc_sem: Semaphore,
    ):
        self.proc_id, self.task_id = proc_id, task_id
        self.sc_sem, self.shm_buf = sc_sem, shm_buf
        self.segments_init(segments)
        self.configs_init(configs)
        self.local_segments_init()

    def segments_init(self, segments: dict[str, Any]) -> None:
        _slice: slice
        segments_subclasses: list[str] = segments.pop("subclasses")
        for name, _slice in segments.items():
            if name not in segments_subclasses:
                raise ValueError(
                    f"{name} not subclass {cfg.ConfigurationSHMSegments.__name__}"
                )

            if name == cfg.ConfigurationFootprint.__name__:
                self.footprint_buf = self.shm_buf[_slice]
            elif name == cfg.ConfigurationMetrics.__name__:
                self.metrics_buf = self.shm_buf[_slice]
            elif name == cfg.ConfigurationRingRawBuf.__name__:
                self.raw_buf = self.shm_buf[_slice]
            elif name == cfg.ConfigurationMonitoring.__name__:
                self.monitoring_buf = self.shm_buf[_slice]

    def configs_init(self, configs: dict[str, Any]) -> None:
        config_subclasses: list[str] = configs.pop("subclasses")
        for name, obj in configs.items():
            if name not in config_subclasses:
                raise ValueError(f"{name} not subclass {cfg.Configuration.__name__}")

            if isinstance(obj, cfg.ConfigurationBacktesting):
                self.cfgBacktesting = obj
            elif isinstance(obj, cfg.ConfigurationFootprint):
                self.cfgFootprint = obj
            elif isinstance(obj, cfg.ConfigurationMetrics):
                self.cfgMetrics = obj
            elif isinstance(obj, cfg.ConfigurationRingRawBuf):
                self.cfgRaw = obj
            elif isinstance(obj, cfg.ConfigurationMonitoring):
                self.cfgMonitoring = obj

    def local_segments_init(self) -> None:
        self.status_buf = self.monitoring_buf[slice(*self.cfgMonitoring.status)]

        self.id_err = self.cfgMonitoring.id_error

        self.time_to_sleep_buf = self.metrics_buf[
            slice(*self.cfgMetrics.time_to_sleep)
        ].cast("q")

    def _for_error_action(self) -> None:
        self.status_buf[self.id_err] = sc.ERROR
        self.sc_sem.release()

    def set_status(self, code: int) -> None:
        if code > sc.ERR_RE:
            self.status_buf[self.proc_id] = code
            self.sc_sem.release()

    def have_problem(self) -> bool:
        if self.status_buf[self.proc_id] > sc.ERR_RE:
            return True

        return False

    def have_task(self) -> bool:
        if self.status_buf[self.task_id] == sc.STOP:
            return True

        return False

    @staticmethod
    def dump_profile(file_path: str, obj: np.ndarray | memoryview, raw=False) -> None:
        """Save ShMemory/NDarray to .bin/.csv"""
        if raw:
            with open(file_path, "wb") as f:
                f.write(obj[:])
        else:
            if isinstance(obj, np.ndarray):
                np.savetxt(
                    file_path,
                    obj,
                    fmt="%d",
                    delimiter=",",
                )
