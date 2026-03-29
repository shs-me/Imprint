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
        pre_sleep_logic: Event,
        general_event: Event,
    ) -> None:
        # Initialization
        self._mo = mo
        self._id_m_ = self._mo._id_m
        self._set, self._get = self._mo.set_, self._mo.get_
        self.pre_sleep_logic: Event = pre_sleep_logic
        self.wait_main: Event = general_event

    @staticmethod
    def create(
        pre_sleep_logic: Event,
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
                mo=mo, pre_sleep_logic=pre_sleep_logic, general_event=general_event
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
        pre_sleep_logic = self.pre_sleep_logic
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
                                pre_sleep_logic.wait()
                                if get_status(id_m, proc=True):
                                    break

                                set_status(id_m, 5)  # Running # TIME WAKE_UP
                                reader._check_update()
                                pre_sleep_logic.clear()
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
    pre_sleep_logic: Event,
    logic_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
):

    gc.disable()
    agent = LogicAgent.create(
        pre_sleep_logic=pre_sleep_logic,
        logic_monitor=logic_monitor,
        general_event=general_event,
        warn_error_status=warn_error_status,
    )
    if isinstance(agent, LogicAgent):
        agent.run_logic_engine()
