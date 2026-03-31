import gc
import traceback
from multiprocessing.synchronize import Event, Semaphore

from ... import Config, MonitorObj
from . import BaseGridReader


class LogicAgent:
    def __init__(
        self,
        mo: MonitorObj,
        reader: BaseGridReader,
        pre_sleep_logic: Event,
        general_event: Event,
    ) -> None:
        self._mo, self.reader = mo, reader

        self.id_m = self._mo.id_m
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.pre_sleep_logic, self.wait_main = pre_sleep_logic, general_event

    def _resolve_reader(self) -> object:
        """Create obj BaseReader or Plugin subclass BaseReader"""
        pass

    def run_logic_engine(self) -> None:
        # LocalLinks
        id_m, set_status, have_problem = self.id_m, self.set_status, self.have_problem
        pre_sleep_logic = self.pre_sleep_logic
        reader = self.reader
        #  - - -
        try:
            while True:
                try:
                    gc.collect()
                    self.wait_main.wait()
                    while True:
                        if have_problem(id_m=id_m, daugther=True) is not True:
                            set_status(id_m, 4)  # IDLE # TIME START
                            pre_sleep_logic.wait()
                            if have_problem(id_m, proc=True):
                                break

                            set_status(id_m, 5)  # Running # TIME WAKE_UP
                            reader._check_update()

                        else:
                            return

                except Exception:
                    traceback.print_exc()  # Debug
                    set_status(id_m, 150)  # Error in this func
                    break

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m, 150)  # Error in this func


def run_logic(
    pre_sleep_logic: Event,
    logic_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    try:
        try:
            mo = MonitorObj(
                proc_name=Config.CoreConfig.Status.logic.__name__,
                warn_error_status=warn_error_status,
                _monitor=logic_monitor,
            )
        except Exception:
            return

        reader = BaseGridReader.create(_mo_=mo, guarantee=pre_sleep_logic)
        if isinstance(reader, BaseGridReader):
            agent = LogicAgent(
                mo=mo,
                reader=reader,
                pre_sleep_logic=pre_sleep_logic,
                general_event=general_event,
            )
            agent.run_logic_engine()
            agent, reader = None, None
            gc.collect()

        else:
            mo.set_status(id_m=mo.id_m, code=151)

    finally:
        gc.collect()
