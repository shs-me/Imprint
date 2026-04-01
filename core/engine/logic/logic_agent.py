import gc
import importlib.util
import inspect
import os
import traceback
from multiprocessing.synchronize import Event, Semaphore

from ... import Config, MonitorObj
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
        self.id_m = self._mo.id_m
        self.set_status, self.have_problem = self._mo.set_status, self._mo.have_problem
        self.pre_sleep_logic, self.wait_main = pre_sleep_logic, general_event

    @staticmethod
    def resolve_reader(mo: MonitorObj, guarentee: Event):
        """Create obj BaseReader or Plugin subclass BaseReader"""
        _path = Config.CorePath.plugin_path
        if not os.path.exists(_path):
            return BaseGridReader(mo=mo, guarantee=guarentee)

        try:
            module_name = os.path.splitext(os.path.basename(_path))[0]
            spec = importlib.util.spec_from_file_location(module_name, _path)
            if spec is not None and spec.loader is not None:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, GridReader) and obj is not GridReader:
                        return obj(mo=mo, guarantee=guarentee)

        except Exception:
            traceback.print_exc()

        return BaseGridReader(mo=mo, guarantee=guarentee)

    def run_logic_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = self._mo.SLEEP, self._mo.WAKE_UP
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
                        if have_problem() is not True:
                            set_status(id_m, SLEEP)  # IDLE # TIME START
                            pre_sleep_logic.wait()
                            if have_problem(proc=True):
                                break

                            set_status(id_m, WAKE_UP)  # Running # TIME WAKE_UP
                            reader._check_update()
                            if pre_sleep_logic.is_set():
                                pre_sleep_logic.clear()

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

        reader = LogicAgent.resolve_reader(mo=mo, guarentee=pre_sleep_logic)
        if isinstance(reader, GridReader):
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
