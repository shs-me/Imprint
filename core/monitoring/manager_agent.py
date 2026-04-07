from multiprocessing.synchronize import Semaphore

import numpy as np

from .. import Config
from .. import ShmBufOffset as sbo
from .. import StatusCodes as sc


class ManagerAgent:
    def __init__(
        self,
        proc_id: int,
        task_id: int,
        shm_buf: memoryview,
        sc_sem: Semaphore,
    ):
        self.cfg = Config.ShmSharing.Monitoring
        self.proc_id, self.task_id = proc_id, task_id
        self.sc_sem, self.shm_buf = sc_sem, shm_buf
        self._buf_sharing()

    def _buf_sharing(self) -> None:
        self.raw_buf = self.shm_buf[slice(*sbo.raw)]
        self.footprint_buf = self.shm_buf[slice(*sbo.footprint)]
        self.metrics_buf = self.shm_buf[slice(*sbo.metrics)]
        self.monitoring_buf = self.shm_buf[slice(*sbo.monitoring)]

        self.status_buf = self.monitoring_buf[slice(*self.cfg.status)]
        self.time_to_sleep_buf = self.metrics_buf[
            slice(*Config.ShmSharing.Metrics.time_to_sleep)
        ].cast("q")

    def _for_error_action(self) -> None:
        self.status_buf[self.cfg.id_error] = sc.ERROR
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
