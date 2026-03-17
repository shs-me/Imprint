import gc
import struct
import time
import traceback
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Event, Semaphore

import numpy as np
from loguru import logger

from . import MonitorObj


class MonitoringAgent:
    def __init__(
        self,
        mo: MonitorObj,
        cfg: dict,
        general_event: Event,
        parser_monitor: Semaphore,
        logic_monitor: Semaphore,
        network_monitor: Semaphore,
    ):
        # Initialization
        self.cfg = cfg
        self.profiling_dump_path = self.cfg["profiling_dump_csv"]
        self._mo = mo
        self.wait_main: Event = general_event

        # AgentsProfiling init
        # Semaphore's
        self.parser_monitor: Semaphore = parser_monitor
        self.logic_monitor: Semaphore = logic_monitor
        self.network_monitor: Semaphore = network_monitor
        # Index's on StatusShm
        self._id_mp: int = self.cfg["status"]["parsing"]["m"]
        self._id_ml: int = self.cfg["status"]["logic"]["m"]
        self._id_mn: int = self.cfg["status"][
            "network_sim" if self.cfg["backtesting"] else "network"
        ]["m"]
        # Items: ID: Semaphore
        self.sems = {
            self._id_mp: parser_monitor,
            self._id_ml: logic_monitor,
            self._id_mn: network_monitor,
        }

        # SHMS
        self._shm: SharedMemory = None  # type: ignore
        self._shm_buf: memoryview = None  # type: ignore

        # ProfilingArray
        self.dglines: int = self._mo.dglines
        self.dgcols: int = self._mo.dgcols
        self.dgarray: np.ndarray = self._mo.dgarray
        self.dgheaders: np.ndarray = self._mo.dgheaders
        # HEADERS L_I_C_T[COL] = LINE[0], ID_MODULE[1], STATUSCODE[2], TIME_NS[3]

    @staticmethod
    def create(
        config: dict,
        general_event: Event,
        parser_monitor: Semaphore,
        logic_monitor: Semaphore,
        network_monitor: Semaphore,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            # Init SHM, profilingArray, StatusSHM
            mo = MonitorObj(
                proc_name="profiling",
                config=config,
                warn_error_status=warn_error_status,
            )
            return MonitoringAgent(
                mo=mo,
                cfg=config,
                general_event=general_event,
                parser_monitor=parser_monitor,
                logic_monitor=logic_monitor,
                network_monitor=network_monitor,
            )

        except Exception:
            traceback.print_exc()
            warn_error_status.release()
            return None

    def _init_session(
        self,
        _dgcols: int,
        _dgheaders: np.ndarray,
        _sems: dict[int, Semaphore],
        _shm_buf: memoryview,
    ) -> None:
        _ids_scs = struct.unpack_from(
            f"!{'i' * (_dgcols * 2)}", _shm_buf[: (_dgcols * 8)]
        )  # index's and status code's
        # Example: (1000 # index in array, 4 status ping, 10001, 5, ...)
        _value = 1
        for _col in range(_dgcols):
            _m_id = int(_shm_buf[(64 + _col)])  # Get ID Module
            _sems[_col] = _sems.pop(_m_id)  # Replaces ID_M, COL

            # Init Headers
            _dgheaders[0, _col] = _ids_scs[_value - 1]  # set index line
            _dgheaders[1, _col] = int(_shm_buf[(64 + _col)])  # set id module
            _dgheaders[2, _col] = (
                _ids_scs[_value] if _ids_scs[_value] != 0 else 4
            )  # set status code ping
            _dgheaders[3, _col] = self.dgarray[
                _ids_scs[_value - 1], _col
            ]  # set time nanosecond

            _value += 2  # next [index+status]

        self.dgheaders = _dgheaders  # Update Headers

    def _read_profile(
        self,
        _col: int,
        _dglines: int,
        _dgarray: np.ndarray,
        _dgheaders: np.ndarray,
    ) -> None:
        _oline, _oscode, _otimens = (
            _dgheaders[0, _col],
            _dgheaders[2, _col],
            _dgheaders[3, _col],
        )
        _nline = (_oline + 1) % _dglines
        # True: Update Headers
        if (_ntimens := _dgarray[_nline, _col]) > _otimens:
            _dgheaders[0, _col] = _nline
            _dgheaders[2, _col] = (_oscode + 1) if (_oscode + 1) != 6 else 4
            _dgheaders[3, _col] = _ntimens

            self.dgheaders = _dgheaders

        # Else: Don't update Headers

    def _profiling(
        self,
        _dglines: int,
        _dgarray: np.ndarray,
        _dgheaders: np.ndarray,
    ) -> None:
        _times = _dgheaders[3]  # Get last ping agents, time_ns
        _max, _min = np.max(_times), np.min(_times)
        # Diff microsecond > 5 second in microsecond == True
        if ((_max - _min) // 1000) > (5000 * 1000):
            _col = int(np.where(_times == _min)[0])  # Get index min on line
            _id_m = _dgheaders[1, _col]  # Get min ID-module
            # ID min not have status Warn & Error in StatusSHM == True
            if self._mo.get_(_id_m) is not True:
                if _dgheaders[2, _col] == 4:  # Sleep when other work
                    self._mo.set_(_id_m, 50)  # Set Status Warn, Module min
                else:  # Maybe stuck after "WakeUp"
                    self._mo.set_(_id_m, 51)  # Set Status Warn, Module min

    def run_profilling_engine(
        self,
    ) -> None:
        # Semaphore, Event - LocalLink
        _sems, _wait_main = self.sems, self.wait_main
        # profilingArray - LocalLinks
        _dgarray, _dgheaders, _dglines, _dgcols, _shm, _shm_buf = (
            self.dgarray,
            self.dgheaders,
            self.dglines,
            self.dgcols,
            self._shm,
            self._shm_buf,
        )
        # Methods - LocalLinks
        _init_session, _read_profile, _profiling = (
            self._init_session,
            self._read_profile,
            self._profiling,
        )
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
                        for _col, _sem in _sems.items():
                            if _count := _sem.get_value() > 0:
                                for _ in range(_count):
                                    _sem.acquire(block=False)
                                    _read_profile(
                                        _col,
                                        _dglines,
                                        _dgarray,
                                        _dgheaders,
                                    )

                        _profiling(
                            _dglines,
                            _dgarray,
                            _dgheaders,
                        )

                    else:
                        if _counter >= 60:
                            self._mo.dump_profile(
                                self.profiling_dump_path, self.dgarray
                            )
                            break

                        _counter += 1
                        time.sleep(1)

            except Exception as e:
                traceback.print_exc()
                logger.error(f"MonitoringAgent | RunMonitoringEngine | {e}")
                break


def run_monitoring(
    config: dict,
    general_event: Event,
    parser_monitor: Semaphore,
    logic_monitor: Semaphore,
    network_monitor: Semaphore,
    warn_error_status: Semaphore,
):
    logger.remove()
    logger.add(
        "logs/monitoring.log",
        rotation="100 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    gc.disable()
    agent = MonitoringAgent.create(
        config=config,
        general_event=general_event,
        parser_monitor=parser_monitor,
        logic_monitor=logic_monitor,
        network_monitor=network_monitor,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, MonitoringAgent):
        agent.run_profilling_engine()
