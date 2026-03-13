import gc
import struct
import sys
import time
import traceback
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Event, Semaphore

import numpy as np
from loguru import logger

from src.utils import StatusAgent as _sa


class MonitoringAgent:
    def __init__(
        self,
        cfg: dict,
        id_info: dict,
        general: dict,
        general_event: Event,
        parser_monitor: Semaphore,
        logic_monitor: Semaphore,
        network_monitor: Semaphore,
    ):
        try:
            self.cfg = cfg

            self.wait_main: Event = general_event

            self.parser_monitor: Semaphore = parser_monitor
            self.logic_monitor: Semaphore = logic_monitor
            self.network_monitor: Semaphore = network_monitor
            self.sems = {
                parser_monitor: 0,
                logic_monitor: 2,
                network_monitor: 6,
            }
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
    ):
        # DebugArrayVariables - LocalLinks
        _id_info, _general, _dgcols, _sems, _minfo = (
            self._id_info,
            self._general,
            self.dgcols,
            self.sems,
            self.minfo,
        )
        # - - -
        _value = 1
        _ids_scs = struct.unpack_from(
            f"!{'i' * (_dgcols * 2)}", _shm_buf[: (_dgcols * 8)]
        )  # index's and status code's
        for col in range(_dgcols):
            _m_id = int(_shm_buf[(64 + col)])
            _minfo[_m_id] = {
                col: {
                    _ids_scs[_value - 1]: _ids_scs[_value]
                    if _ids_scs[_value] != 0
                    else 4
                }
            }  # status code

            _value += 2

        self.minfo = _minfo

    def _check_debug_array(
        self,
        _id,
        _dgarray: np.ndarray,
        _wait_update: Semaphore,
    ):
        # DebugArrayVariables - LocalLinks
        _general, _dglines, _minfo = (
            self._general,
            self.dglines,
            self.minfo,
        )
        # - - -
        for _idx, _value in _minfo[_id].items():
            for _idy, _scode in _value.items():
                _ns = _dgarray[_idy:_idx]
                _minfo[_id][_idx] = {
                    (_idy + 1) % _dglines: _scode + 1 if _scode + 1 != 7 else 4
                }

        self.minfo = _minfo

    def run_monitoring_engine(
        self,
    ):
        # Semaphore, Event - LocalLink
        _sems, _wait_main = self.sems, self.wait_main
        # DebugArray - LocalLinks
        _dgarray, _shm, _shm_buf = self.dgarray, self._shm, self._shm_buf
        # Methods - LocalLinks
        _init_session, _check_dga = self._init_session, self._check_debug_array
        #  - - -
        while True:
            try:
                gc.collect()
                _wait_main.wait()
                _init_session(_shm_buf)
                _counter = 0
                while True:
                    if any(_sem.get_value() > 0 for _sem in _sems.keys()):
                        _counter = 0
                        for _sem, _id_m in _sems.items():
                            if _count := _sem.get_value() > 0:
                                for _ in range(_count):
                                    _sem.acquire(block=False)
                                    # - - -
                    else:
                        if _counter >= 60:
                            _sa.save_array(_shm_buf, "test.bin")
                            break

                        _counter += 1
                        time.sleep(1)

            except Exception as e:
                traceback.print_exc()
                logger.error(f"MonitoringAgent | RunMonitoringEngine | {e}")
                break


def run_monitoring(
    config: dict,
    id_info: dict,
    general: dict,
    general_event: Event,
    parser_monitor: Semaphore,
    logic_monitor: Semaphore,
    network_monitor: Semaphore,
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
        parser_monitor=parser_monitor,
        logic_monitor=logic_monitor,
        network_monitor=network_monitor,
    )
    if isinstance(agent, MonitoringAgent):
        agent.run_monitoring_engine()
