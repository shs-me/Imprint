import gc
import os
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

from .. import MonitorObj
from . import BaseGridReader


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
            return BaseGridReader

        for filename in os.listdir(dauhter_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                _module_name = filename[:-3]
                try:
                    if dauhter_path not in sys.path:
                        sys.path.append(dauhter_path)

                    # . . .

                except Exception:
                    traceback.print_exc()  # Debug

        return BaseGridReader

    def run_logic_engine(
        self,
    ) -> None:
        # StatusAgents - LocalLink
        _id_m_, _set_status, _get_status = self._id_m_, self._set, self._get
        # Semaphore, Event - LocalLink
        _wait_main, _acquire_parser = self.wait_main, self.acquire_parser
        # Methods - LocalLinks
        #  - - -
        try:
            reader = BaseGridReader.create(self.cfg, self._mo)
            if isinstance(reader, BaseGridReader):
                while True:
                    try:
                        gc.collect()
                        _wait_main.wait()
                        while True:
                            if _get_status(_id_m_) is not True:
                                _set_status(_id_m_, 4)  # IDLE # TIME START
                                while _acquire_parser.acquire(block=False):
                                    pass

                                _acquire_parser.acquire()
                                if _get_status(_id_m_, proc=True):
                                    break

                                _set_status(_id_m_, 5)  # Running # TIME WAKE_UP
                                reader._check_update()

                            else:
                                sys.exit()

                    except Exception:
                        traceback.print_exc()  # Debug
                        _set_status(_id_m_, 150)  # Error in this func
                        break
            else:
                _set_status(_id_m_, 151)  # Error in reader
                return

        except Exception:
            traceback.print_exc()  # Debug
            _set_status(_id_m_, 150)  # Error in this func


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
