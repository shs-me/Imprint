import gc
import struct
import sys
import traceback
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Event, Semaphore

import numpy as np
from loguru import logger


class MonitoringAgent:
    def __init__(
        self,
        cfg: dict,
        id_info: dict,
        general: dict,
        general_event: Event,
        sem_sleep_monitoring: Semaphore,
    ):
        try:
            self.cfg = cfg

            self.wait_main = general_event
            self.wait_update = sem_sleep_monitoring
            # Status Codes
            self._general = general
            self._id_info = id_info
            # ShmDebug Init
            self._shm_name: str = "debug"
            self._shm: SharedMemory = None  # type: ignore
            self._shm_buf: memoryview = None  # type: ignore
            self._shm_init()
            # DebugArray
            self.dglines: int = self.cfg["debug"]["lines"]
            self.dgcols: int = self.cfg["debug"]["cols"]
            self.offset: int = self.cfg["debug"]["offset"]
            self.dgarray: np.ndarray = None  # type: ignore

            self._dgc = {}
            self.dgids = {}  # debug array Cols & Lines
            self.minfo = {}  # modules status code's
            self._debug_array_init()

        except Exception as e:
            logger.error(f"MonitoringAgent | __Init__ | {e}")
            sys.exit()

    def _shm_init(
        self,
    ):  # Load SharedMemory-s
        shm = SharedMemory(
            name=self.cfg[self._shm_name]["shm"],
        )
        self._shm = shm
        if shm.buf is not None:
            self._shm_buf = shm.buf

    def _debug_array_init(
        self,
    ):  # Create Array on buffer
        self.dgarray = np.ndarray(
            (self.dglines, self.dgcols),
            dtype=np.int64,
            offset=self.offset,
            buffer=self._shm_buf,
        )

    def _init_session(
        self,
        _shm_buf: memoryview,
        _wait_update: Semaphore,
    ):
        # DebugArrayVariables - LocalLinks
        _id_info, _general, _dgcols, _dgids, _minfo = (
            self._id_info,
            self._general,
            self.dgcols,
            self.dgids,
            self.minfo,
        )
        # - - -
        _counter, _value = 0, 1
        _ids_scs = struct.unpack_from(
            f"!{'i' * (_dgcols * 2)}", _shm_buf[: (_dgcols * 8)]
        )  # index's and status code's
        _value = 1
        for col in range(_dgcols):
            _m_id = int(_shm_buf[(64 + col)])
            _minfo[col] = {_m_id: _ids_scs[_value]}  # status code
            _dgids[col] = _ids_scs[_value - 1]  # line

            _counter += 1 if _dgids[col] == 0 else 0
            _value += 2

        self.dgids, self.minfo = _dgids, _minfo

        if _counter >= _dgcols:
            _wait_update.acquire()

    def _check_debug_array(
        self,
        _dgarray: np.ndarray,
        _wait_update: Semaphore,
    ):
        # DebugArrayVariables - LocalLinks
        _id_info, _general, _dgids, _dglines, _minfo = (
            self._id_info,
            self._general,
            self.dgids,
            self.dglines,
            self.minfo,
        )
        # - - -
        _idy, _idx = list(_dgids.values()), list(_dgids.keys())
        _raw = _dgarray[_idy, _idx]
        _diff = np.diff(_raw)

        #  . . .
        for _ in range(len(_idx)):
            _dgids[_] = (_idy[_] + 1) % _dglines

        print(_dgids[0])
        self.dgids = _dgids

    def run_monitoring_engine(
        self,
    ):
        # Semaphore, Event - LocalLink
        _wait_update, _wait_main = self.wait_update, self.wait_main
        # DebugArray - LocalLinks
        _dgarray, _shm, _shm_buf = self.dgarray, self._shm, self._shm_buf
        # Methods - LocalLinks
        _init_session, _check_dga = self._init_session, self._check_debug_array
        #  - - -
        while True:
            try:
                gc.collect()
                np.savetxt("test.csv", _dgarray, delimiter=",")
                _init_session(_shm_buf, _wait_update)
                while True:
                    _check_dga(_dgarray, _wait_update)

                    for _ in range(9):
                        _wait_update.acquire(block=False)

                    np.savetxt("test.csv", _dgarray, delimiter=",")
                    _wait_update.acquire()

            except Exception as e:
                traceback.print_exc()
                logger.error(f"MonitoringAgent | RunMonitoringEngine | {e}")
                break


def run_monitoring(
    config: dict,
    id_info: dict,
    general: dict,
    general_event: Event,
    sem_sleep_monitoring: Semaphore,
):
    logger.remove()
    logger.add(
        f"logs/{__name__}.log",
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    gc.disable()
    agent = MonitoringAgent(
        cfg=config,
        id_info=id_info,
        general=general,
        general_event=general_event,
        sem_sleep_monitoring=sem_sleep_monitoring,
    )
    if isinstance(agent, MonitoringAgent):
        agent.run_monitoring_engine()
