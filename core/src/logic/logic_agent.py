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
        sleep_logic: Event,
        general_event: Event,
        writer_sleep: Event,
    ) -> None:
        # Initialization
        self._mo = mo
        self._get, self._set, self._id_m_ = (
            self._mo.get_,
            self._mo.set_,
            self._mo._status(daughter=False),
        )

        self.cfg: dict = cfg
        self._algorithm_path: str = "algorithm"
        self.wait_parser: Event = sleep_logic
        self.wait_main: Event = general_event
        self.writer_sleep: Event = writer_sleep

    @staticmethod
    def create(
        cfg: dict,
        sleep_logic: Event,
        logic_monitor: Semaphore,
        general_event: Event,
        writer_sleep: Event,
        warn_error_status: Semaphore,
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
                sleep_logic=sleep_logic,
                general_event=general_event,
                writer_sleep=writer_sleep,
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
        _wait_main, _wait_parser = self.wait_main, self.wait_parser
        # Methods - LocalLinks
        #  - - -
        try:
            reader = BaseGridReader.create(
                cfg=self.cfg, _mo_=self._mo, writer_sleep=self.writer_sleep
            )
            if isinstance(reader, BaseGridReader):
                while True:
                    try:
                        gc.collect()
                        _wait_main.wait()
                        while True:
                            if _get_status(_id_m_) is not True:
                                _set_status(_id_m_, 4)  # IDLE # TIME START
                                _wait_parser.wait()
                                if _get_status(_id_m_, proc=True):
                                    break

                                _set_status(_id_m_, 5)  # Running # TIME WAKE_UP
                                reader._check_update()
                                _wait_parser.clear()
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
    sleep_logic: Event,
    logic_monitor: Semaphore,
    general_event: Event,
    writer_sleep: Event,
    warn_error_status: Semaphore,
):

    gc.disable()
    agent = LogicAgent.create(
        cfg=config,
        sleep_logic=sleep_logic,
        logic_monitor=logic_monitor,
        general_event=general_event,
        writer_sleep=writer_sleep,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, LogicAgent):
        agent.run_logic_engine()
