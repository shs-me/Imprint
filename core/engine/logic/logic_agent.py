import gc
import importlib.util
import inspect
import os
import traceback
from multiprocessing.synchronize import Event, Semaphore

from ... import Config, MonitorObj
from .. import shm_load
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
        self.pre_sleep_logic, self.wait_main = pre_sleep_logic, general_event

    @staticmethod
    def resolve_reader(mo: MonitorObj):
        """Create obj BaseReader or Plugin subclass BaseReader"""
        _path = Config.CorePath.algoritm_path
        if not os.path.exists(_path):
            # for warn
            return BaseGridReader(mo=mo)

        else:
            try:
                module_name = os.path.splitext(os.path.basename(_path))[0]
                spec = importlib.util.spec_from_file_location(module_name, _path)
                if spec is not None and spec.loader is not None:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, GridReader) and obj is not GridReader:
                            return obj(mo=mo)

            except Exception:
                traceback.print_exc()

        return BaseGridReader(mo=mo)

    def run_logic_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = self._mo.SLEEP, self._mo.WAKE_UP
        id_m, set_status, have_problem = self.id_m, self.set_status, self.have_problem
        pre_sleep_logic = self.pre_sleep_logic
        reader, have_watchdog_task = self.reader, self.have_watchdog_task
        #  - - -
        try:
            while True:
                try:
                    gc.collect()
                    self.wait_main.wait()
                    while True:
                        set_status(id_m=id_m, code=SLEEP)
                        pre_sleep_logic.wait()
                        if have_problem() is False:
                            if have_watchdog_task():
                                break

                            set_status(id_m=id_m, code=WAKE_UP)
                            reader._check_update()
                            if pre_sleep_logic.is_set():
                                pre_sleep_logic.clear()

                        else:
                            return

                except Exception:
                    traceback.print_exc()  # Debug
                    set_status(id_m=id_m, code=150)  # Error in this func
                    break

        except Exception:
            traceback.print_exc()  # Debug
            set_status(id_m=id_m, code=150)  # Error in this func


def run_logic(
    pre_sleep_logic: Event,
    logic_monitor: Semaphore,
    general_event: Event,
    warn_error_status: Semaphore,
) -> None:
    gc.disable()
    if (data := shm_load()) is None:
        return

    shm, shm_buf = data
    mo: MonitorObj = MonitorObj(
        shm_buf=shm_buf,
        proc_name=Config.CoreConfig.Status.logic.__name__,
        warn_error_status=warn_error_status,
        monitor=logic_monitor,
    )

    reader = LogicAgent.resolve_reader(mo=mo)
    agent = LogicAgent(
        mo=mo,
        reader=reader,
        pre_sleep_logic=pre_sleep_logic,
        general_event=general_event,
    )
    try:
        agent.run_logic_engine()
    except KeyboardInterrupt:
        pass
    del agent, reader, mo
    shm_buf.release()
    shm.close()
    gc.collect()
