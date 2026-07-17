import gc
import time
from multiprocessing.synchronize import Semaphore

from ... import configurations as cfg
from .status_codes import StatusCodes as scs


class AgentManager:
    cfgBacktesting: cfg.cfgBacktesting
    cfgAccount: cfg.cfgAccount
    cfgFootprint: cfg.cfgFootprint
    cfgMetrics: cfg.cfgMetrics
    cfgDataStream: cfg.cfgDataStream
    cfgUserStream: cfg.cfgUserStream
    cfgSignal: cfg.cfgSignal

    def __init__(
        self,
        proc_id: int,
        task_id: int,
        segments: dict[str, slice],
        configs: list,
        shm_buf: memoryview,
        sc_sem: Semaphore,
        symbol: str,
    ) -> None:
        self._proc_id, self._task_id = proc_id, task_id
        self._sc_sem, self._shm_buf = sc_sem, shm_buf
        self._segments = segments

        self.configs_init(configs)

        self.symbol: str = symbol
        self.task_status: memoryview = self.cfgMetrics.status.cast("q")[
            task_id : task_id + 1
        ]
        self.proc_status: memoryview = self.cfgMetrics.status.cast("q")[
            proc_id : proc_id + 1
        ]

    def configs_init(self, configs: list) -> None:
        for attr_name, attr_type in self.__annotations__.items():
            for obj in configs:
                if isinstance(obj, attr_type):
                    setattr(self, attr_name, obj)
                    if issubclass(obj.__class__, cfg.cfgSHMSegments):
                        self.bind_shm_segments(obj)
                    break

    def bind_shm_segments(self, cfg: object) -> None:
        for attr_name in list(cfg.__dict__.keys()):
            attr_val = getattr(cfg, attr_name)
            if isinstance(attr_val, tuple):
                if len(attr_val) == 2:
                    shm: memoryview = self._shm_buf[
                        self._segments[cfg.__class__.__name__]
                    ]
                    setattr(cfg, attr_name, shm[slice(*attr_val)])

    def set_text(self, text: str) -> None:
        text_buf: memoryview = self.cfgMetrics.text
        b_text, start = text.encode(), self._proc_id * self.cfgMetrics.text_size
        set_len, start = text_buf[start : start + 8].cast("q"), start + 8
        set_len[0] = len(b_text)
        text_buf[start : start + len(b_text)] = b_text

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
        self._sc_sem.release()

    def set_task_sc(self, code: scs | int) -> None:
        self.task_status[0] |= code

    def clear_task_sc(self, code: scs | int) -> None:
        self.task_status[0] &= ~(code)

    def _for_error_action(self) -> None:
        self.proc_status[0] |= scs.ERROR
        self._sc_sem.release()
