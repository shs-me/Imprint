import gc
import os
import struct
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

from .. import MonitorObj
from . import BaseFootprintReader


class LogicAgent:
    def __init__(
        self,
        mo: MonitorObj,
        cfg: dict,
        sem_sleep_logic: Semaphore,
        general_event: Event,
    ) -> None:
        # Initialization
        self._mo = mo
        self._get, self._set, self._id_m_ = (
            self._mo.get_,
            self._mo.set_,
            self._mo._status(daughter=False),
        )

        self.cfg = cfg
        self._algorithm_path = "algorithm"
        self.acquire_parser = sem_sleep_logic
        self.wait_main = general_event

        # MetricsSHM.buf
        self.metrics_buf = self._mo.shms["metrics"]["buf"]
        # Offsets
        self._metrics_buf: memoryview = self._mo.shms["metrics"]["buf"]
        self._id_y_x_offset: int = self.cfg["metrics"]["id_y_x"]

        self._flag_r: int = self.cfg["metrics"]["flag_r"]
        self._flag_w: int = self.cfg["metrics"]["flag_w"]

    @staticmethod
    def create(
        cfg: dict,
        sem_sleep_logic: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
        logic_monitor: Semaphore,
    ) -> object | None:
        try:
            # Init SHM, profilingArray, StatusSHM
            mo = MonitorObj(
                proc_name="logic",
                config=cfg,
                warn_error_status=warn_error_status,
                _monitor=logic_monitor,
            )
            return LogicAgent(
                mo=mo,
                cfg=cfg,
                sem_sleep_logic=sem_sleep_logic,
                general_event=general_event,
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    # Get BaseReader Or Plagins
    def _resolve_reader(self, dauhter_path):
        if not os.path.exists(dauhter_path):
            return BaseFootprintReader

        for filename in os.listdir(dauhter_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                _module_name = filename[:-3]
                try:
                    if dauhter_path not in sys.path:
                        sys.path.append(dauhter_path)

                    # . . .

                except Exception:
                    traceback.print_exc()  # Debug

        return BaseFootprintReader

    # Get ID-X : ID-Y from buffer
    # WARN: This Func Have SpinLock
    def _get_raw_metrics(
        self,
        _metrics_buf: memoryview,
        _ids: int,
        _flag_r: int,
        _flag_w: int,
        _set_status,
        _id_m_: int,
    ) -> tuple[int, int] | bool | None:
        try:
            while _metrics_buf[_flag_w] == 5:  # Working w...
                pass

            if _metrics_buf[_flag_w] == 4:  # Idle w
                _metrics_buf[_flag_r] = 5  # Working r...
                ids: tuple[int, int] = struct.unpack_from(
                    "!qq", _metrics_buf[_ids : (8 * 2 + _ids)]
                )
                _metrics_buf[_flag_r] = 4  # Idle r
                return ids

        except Exception:
            traceback.print_exc()  # Debug
            _set_status(_id_m_, 152)
            return False

    def run_logic_engine(
        self,
    ):
        # JSON Decoder, SHM.Buf
        _metrics_buf = self.metrics_buf
        # BaseInit - LocalLink
        _ids, _flag_r, _flag_w = self._id_y_x_offset, self._flag_r, self._flag_w
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = self._id_m_, self._set, self._get
        # Semaphore, Event - LocalLink
        _wait_main, _acquire_parser = self.wait_main, self.acquire_parser
        # Methods - LocalLinks
        _get_raw_metrics, _resolve_reader = self._get_raw_metrics, self._resolve_reader
        # Other - LocalLinks
        _algorithm_path = self._algorithm_path
        # - - -
        while True:
            try:
                gc.collect()

                _wait_main.wait()
                _ObjReader = _resolve_reader(_algorithm_path)
                reader = _ObjReader()
                if issubclass(_ObjReader, BaseFootprintReader):
                    while True:
                        if _get_status(_id_m_) is not True:
                            _set_status(_id_m_, 4)  # Sleep
                            _acquire_parser.acquire()
                            if _get_status(_id_m_, proc=True):
                                break

                            _set_status(_id_m_, 5)  # WakeUp
                            while _acquire_parser.acquire(block=False):
                                pass

                            if isinstance(
                                (
                                    ids := _get_raw_metrics(
                                        _metrics_buf,
                                        _ids,
                                        _flag_r,
                                        _flag_w,
                                        _set_status,
                                        _id_m_,
                                    )
                                ),
                                tuple,
                            ):
                                reader.check_patterns(ids[0], ids[1])

                            else:
                                if ids is False:
                                    sys.exit()

                        else:
                            sys.exit()
                else:
                    _set_status(_id_m_, 151)  # Error in reading
                    break

            except Exception:
                traceback.print_exc()  # Debug
                _set_status(_id_m_, 150)  # Error in this func
                break


def run_logic(
    config: dict,
    sem_sleep_logic: Semaphore,
    logic_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
):

    gc.disable()
    agent = LogicAgent.create(
        cfg=config,
        sem_sleep_logic=sem_sleep_logic,
        logic_monitor=logic_monitor,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, LogicAgent):
        agent.run_logic_engine()
