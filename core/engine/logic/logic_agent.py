import gc
import importlib.util
import inspect
import os
from multiprocessing.synchronize import Event, Semaphore

from ... import Config, MonitorObj
from ... import StatusCodes as sc
from .. import error_action, shm_manager
from . import BaseGridReader, GridReader


class LogicAgent:
    def __init__(
        self,
        mo: MonitorObj,
        reader: GridReader,
        pre_sleep_logic: Event,
        general_event: Event,
    ) -> None:
        self._mo, self.reader = mo, reader
        self.id_m, self.have_watchdog_task = self._mo.id_m, self._mo.have_watchdog_task
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.status_buf = self._mo.status_buf
        self.pre_sleep_logic, self.wait_main = pre_sleep_logic, general_event

    @staticmethod
    def resolve_reader(mo: MonitorObj):
        """Create obj BaseReader or Plugin subclass BaseReader"""
        _path = Config.CorePath.algoritm_path
        if not os.path.exists(_path):
            return BaseGridReader(mo=mo)

        else:

            @error_action()
            def get_plugin():
                module_name = os.path.splitext(os.path.basename(_path))[0]
                spec = importlib.util.spec_from_file_location(module_name, _path)
                if spec is not None and spec.loader is not None:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, GridReader) and obj is not GridReader:
                            return obj(mo=mo)

            result = get_plugin()
            if result is not None:
                return result

        return BaseGridReader(mo=mo)

    def _alarm_clock(self, sleeper: Event) -> bool:
        if sleeper.is_set() is False:
            return True
        else:
            return False

    @error_action(set_sc_code=True)
    def run_logic_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        id_m, set_status, have_problem = self.id_m, self.set_status, self.have_problem
        pre_sleep_logic, alarm_clock = self.pre_sleep_logic, self._alarm_clock
        reader, have_watchdog_task = self.reader, self.have_watchdog_task
        #  - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            while True:
                set_status(id_m=id_m, code=SLEEP)
                if have_problem() is False:
                    if have_watchdog_task():
                        break

                    if alarm_clock(sleeper=pre_sleep_logic):
                        pre_sleep_logic.wait()
                        continue

                    set_status(id_m=id_m, code=WAKE_UP)
                    reader._check_update()
                    if pre_sleep_logic.is_set():
                        pre_sleep_logic.clear()

                else:
                    return


@shm_manager(create=False)
def run_logic(
    logic_event: Event,
    general_event: Event,
    sc_sem: Semaphore,
    **kwargs,
) -> None:
    mo: MonitorObj = MonitorObj(
        proc_name=Config.CoreConfig.Status.logic.__name__,
        shm_buf=kwargs["shm_buf"],
        sc_sem=sc_sem,
    )
    reader = LogicAgent.resolve_reader(mo=mo)
    agent = LogicAgent(
        mo=mo,
        reader=reader,
        pre_sleep_logic=logic_event,
        general_event=general_event,
    )
    agent.run_logic_engine()
