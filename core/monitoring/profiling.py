import gc
import socket
import struct
import time
import traceback
from multiprocessing.synchronize import Event, Semaphore

import numpy as np
from loguru import logger

from .. import Config
from . import MonitorObj

# Configuration
UDP_IP = "127.0.0.1"
UDP_PORT = 5005
DELAY = 0.1  # 10ms interval


class MonitoringAgent:
    def __init__(
        self,
        backtesting: bool,
        mo: MonitorObj,
        general_event: Event,
        parser_monitor: Semaphore,
        logic_monitor: Semaphore,
        network_monitor: Semaphore,
    ) -> None:
        # Initialization
        self.profiling_dump_path = Config.CorePath.profiling_csv
        self.pheaders_dump_path = Config.CorePath.pheaders_csv
        self._mo = mo
        self.wait_main = general_event
        # Semaphore's
        self.parser_monitor = parser_monitor
        self.logic_monitor = logic_monitor
        self.network_monitor = network_monitor
        # Index's on StatusShm
        self._id_mp = Config.CoreConfig.Status.parsing.id_m
        self._id_ml = Config.CoreConfig.Status.logic.id_m
        if backtesting:
            self._id_mn = Config.CoreConfig.Status.network_sim.id_m
        else:
            self._id_mn = Config.CoreConfig.Status.network.id_m

        # Items: ID: Semaphore
        self.sems = {
            self._id_mp: parser_monitor,
            self._id_ml: logic_monitor,
            self._id_mn: network_monitor,
        }

        # SHMS
        self.shm_buf: memoryview = self._mo._profiling_buf
        # ProfilingArray
        self.dglines: int = self._mo.dglines
        self.dgcols: int = self._mo.dgcols
        self.dgarray: np.ndarray = self._mo.dgarray
        self.dgheaders: np.ndarray = self._mo.dgheaders
        # HEADERS ROW[0]LINE, ROW[1]ID_MODULE, ROW[2]STATUSCODE, ROW[3]TIME_NS
        # ROW4[4]DIFF_WAIT, ROW[5]DIFF_WORK

    @staticmethod
    def create(
        backtesting: bool,
        general_event: Event,
        parser_monitor: Semaphore,
        logic_monitor: Semaphore,
        network_monitor: Semaphore,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Profiling.__name__,
                warn_error_status=warn_error_status,
            )
            return MonitoringAgent(
                backtesting=backtesting,
                mo=mo,
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
        cols: int,
        dgheaders: np.ndarray,
        sems: dict[int, Semaphore],
        shm_buf: memoryview,
    ) -> None:
        ids_scs = struct.unpack_from(
            f"!{'i' * (cols * 2)}", shm_buf[: (cols * 8)]
        )  # index's and status code's
        # Example: (1000 # index in array, 4 status ping, 10001, 5, ...)
        _value = 1
        for _col in range(cols):
            m_id = int(shm_buf[(64 + _col)])  # Get ID Module
            sems[_col] = sems.pop(m_id)  # Replaces ID_M, COL

            # Init Headers
            dgheaders[0, _col] = ids_scs[_value - 1]  # set index line
            dgheaders[1, _col] = int(shm_buf[(64 + _col)])  # set id module
            dgheaders[2, _col] = (
                ids_scs[_value] if ids_scs[_value] != 0 else 4
            )  # set status code ping
            dgheaders[3, _col] = self.dgarray[
                ids_scs[_value - 1], _col
            ]  # set time nanosecond
            dgheaders[4, _col] = 0  # set diff_wait
            dgheaders[5, _col] = 0  # set diff_work

            _value += 2  # next [index+status]

    def _reset_headers(self, _dgheaders: np.ndarray, _dgcols: int) -> None:
        for _col in range(_dgcols):
            _dgheaders[0, _col] = 0
            _dgheaders[2, _col] = 4
            _dgheaders[3, _col] = 0

    def _read_profile(
        self, _col: int, lines: int, dgarray: np.ndarray, dgheaders: np.ndarray
    ) -> None:
        oline: int = dgheaders[0, _col]
        oscode: int = dgheaders[2, _col]
        otimens: int = dgheaders[3, _col]
        nline: int = (oline + 1) % lines
        # True: Update Headers
        if (ntimens := dgarray[nline, _col]) > otimens:
            dgheaders[0, _col] = nline
            dgheaders[2, _col] = (oscode + 1) if (oscode + 1) != 6 else 4
            dgheaders[3, _col] = ntimens
            if 0 < otimens:
                diff_wait_or_work: int = (ntimens - otimens) // 1000
                if oscode == 4:
                    dgheaders[4, _col] = diff_wait_or_work
                if oscode == 5:
                    dgheaders[5, _col] = diff_wait_or_work

        # Else: Don't update Headers

    def _profiling(
        self, lines: int, dgarray: np.ndarray, dgheaders: np.ndarray, send_udp
    ) -> None:
        _times: np.ndarray = dgheaders[3]  # Get last ping agents, time_ns
        arr = np.where(_times == 0)[0]

        if len(arr) > 0:
            # - - -
            return

        # print(dgheaders[0, 2], dgheaders[0, 0], dgheaders[0, 1], flush=True)
        # print(dgheaders[4, 2], dgheaders[4, 0], dgheaders[4, 1], "\n", flush=True)
        send_udp(dgheaders[4, 2], dgheaders[4, 0], dgheaders[4, 1])
        _diff_wss_parser, _diff_parser_logic = (
            int((_times[0] - _times[2]) // 1000),
            int((_times[1] - _times[0]) // 1000),
        )
        _max, _min = np.max(_times), np.min(_times)
        # Diff microsecond > 5 second in microsecond == True
        if int((_max - _min) // 1000) > (5000 * 1000):
            _col = int(np.where(_times == _min)[0][0])  # Get index min on line
            id_m = dgheaders[1, _col]  # Get min ID-module
            # ID min not have status Warn & Error in StatusSHM == True
            if self._mo.get_(id_m) is not True:
                if dgheaders[2, _col] == 4:  # Sleep when other work
                    self._mo.set_(id_m, 50)  # Set Status Warn, Module min
                else:  # Maybe stuck after "WakeUp"
                    self._mo.set_(id_m, 51)  # Set Status Warn, Module min

    def _send_udp(self, val1, val2, val3) -> None:
        data = struct.pack("!qqq", val1, val2, val3)
        self.sock.sendto(data, (UDP_IP, UDP_PORT))

    def run_profilling_engine(self) -> None:
        # LocalLink
        _sems, _wait_main, _shm_buf = self.sems, self.wait_main, self.shm_buf
        _dgarray, _dgheaders = self.dgarray, self.dgheaders
        _dglines, _dgcols = self.dglines, self.dgcols
        _init_session, _reset_headers = self._init_session, self._reset_headers
        _read_profile, _profiling = self._read_profile, self._profiling
        # - - -
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _send_udp = self._send_udp
        while True:
            try:
                gc.collect()
                _wait_main.wait()
                _init_session(
                    cols=_dgcols,
                    dgheaders=_dgheaders,
                    sems=_sems,
                    shm_buf=_shm_buf,
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
                                        _col=_col,
                                        lines=_dglines,
                                        dgarray=_dgarray,
                                        dgheaders=_dgheaders,
                                    )

                        _profiling(
                            lines=_dglines,
                            dgarray=_dgarray,
                            dgheaders=_dgheaders,
                            send_udp=_send_udp,
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
    backtesting: bool,
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
        backtesting=backtesting,
        general_event=general_event,
        parser_monitor=parser_monitor,
        logic_monitor=logic_monitor,
        network_monitor=network_monitor,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, MonitoringAgent):
        agent.run_profilling_engine()
