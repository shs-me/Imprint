import gc
import socket
import struct
import time
import traceback
from multiprocessing.synchronize import Event, Semaphore

import numpy as np
from loguru import logger

from . import MonitorObj

# Configuration
UDP_IP = "127.0.0.1"
UDP_PORT = 5005
DELAY = 0.1  # 10ms interval


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
        self.pheaders_dump_path = self.cfg["pheaders_dump_csv"]
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
        self.profiling_buf: memoryview = self._mo._profiling_buf

        # ProfilingArray
        self.dglines: int = self._mo.dglines
        self.dgcols: int = self._mo.dgcols
        self.dgarray: np.ndarray = self._mo.dgarray
        self.dgheaders: np.ndarray = self._mo.dgheaders
        # HEADERS ROW[0]LINE, ROW[1]ID_MODULE, ROW[2]STATUSCODE, ROW[3]TIME_NS
        # ROW4[4]DIFF_WAIT, ROW[5]DIFF_WORK

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
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    def _init_session(
        self,
        _dgcols: int,
        _dgheaders: np.ndarray,
        _sems: dict[int, Semaphore],
        profiling_buf: memoryview,
    ) -> None:
        _ids_scs = struct.unpack_from(
            f"!{'i' * (_dgcols * 2)}", profiling_buf[: (_dgcols * 8)]
        )  # index's and status code's
        # Example: (1000 # index in array, 4 status ping, 10001, 5, ...)
        _value = 1
        for _col in range(_dgcols):
            _m_id = int(profiling_buf[(64 + _col)])  # Get ID Module
            _sems[_col] = _sems.pop(_m_id)  # Replaces ID_M, COL

            # Init Headers
            _dgheaders[0, _col] = _ids_scs[_value - 1]  # set index line
            _dgheaders[1, _col] = int(profiling_buf[(64 + _col)])  # set id module
            _dgheaders[2, _col] = (
                _ids_scs[_value] if _ids_scs[_value] != 0 else 4
            )  # set status code ping
            _dgheaders[3, _col] = self.dgarray[
                _ids_scs[_value - 1], _col
            ]  # set time nanosecond
            _dgheaders[4, _col] = 0  # set diff_wait
            _dgheaders[5, _col] = 0  # set diff_work

            _value += 2  # next [index+status]

    def _reset_headers(
        self,
        _dgheaders: np.ndarray,
        _dgcols: int,
    ) -> None:
        for _col in range(_dgcols):
            _dgheaders[0, _col] = 0
            _dgheaders[2, _col] = 4
            _dgheaders[3, _col] = 0

        self.dgheaders = _dgheaders

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
            if 0 < _otimens < _ntimens:
                diff_wait_or_work: int = (_ntimens - _otimens) // 1000
                if _oscode == 4:
                    _dgheaders[4, _col] = diff_wait_or_work
                if _oscode == 5:
                    _dgheaders[5, _col] = diff_wait_or_work

        # Else: Don't update Headers

    def _profiling(
        self,
        _dglines: int,
        _dgarray: np.ndarray,
        _dgheaders: np.ndarray,
        _send_udp,
    ) -> None:
        _times: np.ndarray = _dgheaders[3]  # Get last ping agents, time_ns
        arr = np.where(_times == 0)[0]

        if len(arr) > 0:
            # - - -
            return

        # print(_dgheaders[5, 2], _dgheaders[5, 0], _dgheaders[5, 1])
        _send_udp(_dgheaders[5, 2], _dgheaders[5, 0], _dgheaders[5, 1])
        _diff_wss_parser, _diff_parser_logic = (
            int((_times[0] - _times[2]) // 1000),
            int((_times[1] - _times[0]) // 1000),
        )
        _max, _min = np.max(_times), np.min(_times)
        # Diff microsecond > 5 second in microsecond == True
        if int((_max - _min) // 1000) > (5000 * 1000):
            _col = int(np.where(_times == _min)[0][0])  # Get index min on line
            _id_m = _dgheaders[1, _col]  # Get min ID-module
            # ID min not have status Warn & Error in StatusSHM == True
            if self._mo.get_(_id_m) is not True:
                if _dgheaders[2, _col] == 4:  # Sleep when other work
                    self._mo.set_(_id_m, 50)  # Set Status Warn, Module min
                else:  # Maybe stuck after "WakeUp"
                    self._mo.set_(_id_m, 51)  # Set Status Warn, Module min

    def _send_udp(self, val1, val2, val3) -> None:
        data = struct.pack("!qqq", val1, val2, val3)
        self.sock.sendto(data, (UDP_IP, UDP_PORT))

    def run_profilling_engine(
        self,
    ) -> None:
        # Semaphore, Event - LocalLink
        _sems, _wait_main = self.sems, self.wait_main
        # profilingArray - LocalLinks
        _dgarray, _dgheaders, _dglines, _dgcols, profiling_buf = (
            self.dgarray,
            self.dgheaders,
            self.dglines,
            self.dgcols,
            self.profiling_buf,
        )
        # Methods - LocalLinks
        _init_session, _reset_headers, _read_profile, _profiling = (
            self._init_session,
            self._reset_headers,
            self._read_profile,
            self._profiling,
        )
        # - - -
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _send_udp = self._send_udp
        while True:
            try:
                gc.collect()
                _wait_main.wait()
                _init_session(
                    _dgcols,
                    _dgheaders,
                    _sems,
                    profiling_buf,
                )
                _counter = 0
                while True:
                    if any(_sem.get_value() > 0 for _sem in _sems.values()):
                        _counter = 0
                        for _col, _sem in _sems.items():
                            if (_count := _sem.get_value()) > 0:
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
                            _send_udp,
                        )

                    else:
                        if _counter >= 60:
                            self._mo.dump_profile(
                                self.profiling_dump_path,
                                self.dgarray,
                            )
                            self._mo.dump_profile(
                                self.pheaders_dump_path,
                                self.dgheaders,
                            )
                            _reset_headers(
                                _dgheaders,
                                _dgcols,
                            )
                            logger.warning("MonitorAgent | STOPING")
                            break

                        _counter += 1
                        time.sleep(1)

            except Exception as e:
                traceback.print_exc()  # Debug
                logger.error(f"MonitoringAgent | RunMonitoringEngine | {e}")
            finally:
                self.sock.close()
                break


def run_monitoring(
    config: dict,
    general_event: Event,
    parser_monitor: Semaphore,
    logic_monitor: Semaphore,
    network_monitor: Semaphore,
    warn_error_status: Semaphore,
) -> None:
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
