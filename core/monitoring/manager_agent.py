import time
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
        self.lines, self.cols = self.cfg.lines, self.cfg.cols
        self.proc_id, self.task_id = proc_id, task_id
        self.sc_sem, self.shm_buf = sc_sem, shm_buf
        self.dgid = 0
        self._buf_sharing()
        self._init_array()

    def _buf_sharing(self) -> None:
        self.raw_buf = self.shm_buf[slice(*sbo.raw)]
        self.footprint_buf = self.shm_buf[slice(*sbo.footprint)]
        self.metrics_buf = self.shm_buf[slice(*sbo.metrics)]
        self.monitoring_buf = self.shm_buf[slice(*sbo.monitoring)]
        self.status_buf = self.shm_buf[slice(*self.cfg.status)]

    def _init_array(self) -> None:
        self.profils = np.ndarray(
            (self.lines, self.cols),
            dtype=np.int64,
            buffer=self.monitoring_buf[slice(*self.cfg.profiling)],
        )

    def _for_error_action(self) -> None:
        self.status_buf[self.cfg.id_error] = sc.ERROR
        self.sc_sem.release()

    def set_status(self, code: int) -> None:
        if code > sc.ERR_RE:
            self.status_buf[self.proc_id] = code
            self.sc_sem.release()
        else:
            self.profiling()

    def profiling(self) -> None:
        dgid_m = self.dgid
        # - - -
        self.profils[dgid_m, self.proc_id] = time.perf_counter_ns()
        self.dgid = (dgid_m + 1) % self.lines

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
