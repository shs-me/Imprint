import gc
import struct
import sys
import time
import traceback
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Event, Semaphore

import numpy as np
from loguru import logger

from src import MonitorObj as _mo


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

            self._id_mp: int = self.cfg["status"]["parsing"]["m"]
            self._id_ml: int = self.cfg["status"]["logic"]["m"]
            self._id_mn: int = self.cfg["status"][
                "network_sim" if self.cfg["backtesting"] else "network"
            ]["m"]
            self.sems = {
                self._id_mp: parser_monitor,
                self._id_ml: logic_monitor,
                self._id_mn: network_monitor,
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
            self.dgheaders: np.ndarray = None  # type: ignore
            # HEADERS C_L_I_C_T[COL] = COL[0], LINE[1], ID_MODULE[2], STATUSCODE[3], TIME_NS[4]
            self._dgc = {}
            self.dgids = {}  # debug array Cols & Lines
            self.minfo = {}  # modules status code's
            self._debug_array_init()

        except Exception as e:
            traceback.print_exc()
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
        self.dgheaders = np.ndarray((self.dgcols, 5), dtype=np.int64)
        self.dgheaders[:] = 0

    def _init_session(
        self,
        _dgcols: int,
        _dgheaders: np.ndarray,
        _sems: dict[int, Semaphore],
        _shm_buf: memoryview,
    ):
        # DebugArrayVariables - LocalLinks
        # - - -
        _value = 1
        _ids_scs = struct.unpack_from(  # index's and status code's
            f"!{'i' * (_dgcols * 2)}", _shm_buf[: (_dgcols * 8)]
        )  # index's and status code's
        for _row_col in range(_dgcols):
            _m_id = int(_shm_buf[(64 + _row_col)])
            if _m_id in _sems:
                _sems[_row_col] = _sems.pop(_m_id)
                print(_m_id, _sems)

            _dgheaders[_row_col] = (
                _row_col,  # index col
                _ids_scs[_value - 1],  # index line
                int(_shm_buf[(64 + _row_col)]),  # module id
                _ids_scs[_value] if _ids_scs[_value] != 0 else 4,  # status code
                self.dgarray[_ids_scs[_value - 1], _row_col],  # time ns
            )
            _value += 2

        print(_sems)
        print(_dgheaders)
        self.dgheaders = _dgheaders

    def _read_dg_ndarray(
        self,
        _row_col: int,
        _dglines: int,
        _dgarray: np.ndarray,
        _dgheaders: np.ndarray,
    ):
        _oline, _oscode, _otimens = (
            _dgheaders[_row_col, 1],
            _dgheaders[_row_col, 3],
            _dgheaders[_row_col, 4],
        )
        _nline = (_oline + 1) % _dglines
        if _ntimens := _dgarray[_nline, _row_col] > _otimens:
            _dgheaders[_row_col, 1] = _nline
            _dgheaders[_row_col, 3] = (_oscode + 1) if (_oscode + 1) != 7 else 4
            _dgheaders[_row_col, 4] = _ntimens
            self.dgheaders = _dgheaders

    def _read_dg_headers(
        self,
        _dglines: int,
        _dgarray: np.ndarray,
        _dgheaders: np.ndarray,
    ):
        pass

    def run_monitoring_engine(
        self,
    ):
        # Semaphore, Event - LocalLink
        _sems, _wait_main = self.sems, self.wait_main
        # DebugArray - LocalLinks
        _dgarray, _dgheaders, _dglines, _dgcols, _shm, _shm_buf = (
            self.dgarray,
            self.dgheaders,
            self.dglines,
            self.dgcols,
            self._shm,
            self._shm_buf,
        )
        # Methods - LocalLinks
        _init_session, _read_dgnda = self._init_session, self._read_dg_ndarray
        #  - - -
        while True:
            try:
                gc.collect()
                _wait_main.wait()
                _init_session(_dgcols, _dgheaders, _sems, _shm_buf)
                _counter = 0
                while True:
                    if any(_sem.get_value() > 0 for _sem in _sems.values()):
                        _counter = 0
                        for _row_col, _sem in _sems.items():
                            if _count := _sem.get_value() > 0:
                                for _ in range(_count):
                                    _sem.acquire(block=False)
                                    _read_dgnda(
                                        _row_col,
                                        _dglines,
                                        _dgarray,
                                        _dgheaders,
                                    )
                                    # - - -
                    else:
                        if _counter >= 60:
                            _mo.dump_debug_shm(_shm_buf, "test.bin")
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
        "logs/monitoring.log",
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
