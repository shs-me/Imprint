import gc
import sys
import traceback
from multiprocessing.synchronize import Event, Semaphore

from ... import Config, MonitorObj
from . import BaseGridReader


class LogicAgent:
    def __init__(
        self,
        mo: MonitorObj,
        sleep_logic: Event,
        general_event: Event,
    ) -> None:
        # Initialization
        self._mo = mo
        self._id_m_ = self._mo._id_m
        self._set, self._get = self._mo.set_, self._mo.get_
        self.wait_parser: Event = sleep_logic
        self.wait_main: Event = general_event

    @staticmethod
    def create(
        sleep_logic: Event,
        logic_monitor: Semaphore,
        general_event: Event,
        warn_error_status: Semaphore,
    ) -> object | None:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.logic.__name__,
                warn_error_status=warn_error_status,
                _monitor=logic_monitor,
            )
            return LogicAgent(
                mo=mo, sleep_logic=sleep_logic, general_event=general_event
            )

        except Exception:
            traceback.print_exc()  # Debug
            warn_error_status.release()
            return None

    def _resolve_reader(self, dauhter_path) -> object:
        """Create obj BaseReader or Plugin subclass BaseReader"""
        pass

    def run_logic_engine(self) -> None:
        # LocalLinks
        id_m, set_status, get_status = self._id_m_, self._set, self._get
        wait_parser = self.wait_parser
        #  - - -
        try:
            reader = BaseGridReader.create(_mo_=self._mo)
            if isinstance(reader, BaseGridReader):
                while True:
                    try:
                        gc.collect()
                        self.wait_main.wait()
                        while True:
                            if get_status(id_m) is not True:
                                set_status(id_m, 4)  # IDLE # TIME START
                                wait_parser.wait()
                                if get_status(id_m, proc=True):
                                    break

                                set_status(id_m, 5)  # Running # TIME WAKE_UP
                                reader._check_update()
                                wait_parser.clear()
                            else:
                                sys.exit()

                    except Exception:
                        traceback.print_exc()  # Debug
                        set_status(id_m, 150)  # Error in this func
                        break
            else:
                set_status(id_m, 151)  # Error in reader
                return

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m, 150)  # Error in this func


def run_logic(
    sleep_logic: Event,
    logic_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
):

    gc.disable()
    agent = LogicAgent.create(
        sleep_logic=sleep_logic,
        logic_monitor=logic_monitor,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, LogicAgent):
        agent.run_logic_engine()
