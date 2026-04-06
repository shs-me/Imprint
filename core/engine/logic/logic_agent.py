import gc
import importlib.util
import inspect
import os
from multiprocessing.synchronize import Event

from ... import Config, ManagerAgent
from ... import StatusCodes as sc
from .. import error_action, manager_office
from . import BaseFootprintReader, FootprintReader


class LogicAgent:
    def __init__(
        self,
        manager: ManagerAgent,
        reader: FootprintReader,
        pre_sleep_logic: Event,
        general_event: Event,
    ) -> None:
        self.manager, self.reader = manager, reader
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.status_buf = self.manager.status_buf
        self.pre_sleep_logic, self.wait_main = pre_sleep_logic, general_event

    @staticmethod
    def resolve_reader(manager: ManagerAgent):
        path = Config.CorePath.algoritm_path
        if not os.path.exists(path):
            return BaseFootprintReader(manager=manager)
        else:

            @error_action()
            def get_plugin():
                module_name = os.path.splitext(os.path.basename(path))[0]
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is not None and spec.loader is not None:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, FootprintReader):
                            if obj is not FootprintReader:
                                return obj(manager=manager)

            result = get_plugin()
            if result is not None:
                return result

        return BaseFootprintReader(manager=manager)

    def _alarm_clock(self, sleeper: Event) -> bool:
        if sleeper.is_set() is False:
            return True
        else:
            return False

    @error_action(set_sc=True)
    def run_logic_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        set_status, have_problem = self.set_status, self.have_problem
        pre_sleep_logic, alarm_clock = self.pre_sleep_logic, self._alarm_clock
        reader, have_task = self.reader, self.have_task
        #  - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            init_session = True
            while True:
                set_status(code=SLEEP)
                if have_problem() is False:
                    if have_task():
                        break

                    if alarm_clock(sleeper=pre_sleep_logic):
                        pre_sleep_logic.wait()
                        continue

                    set_status(code=WAKE_UP)
                    if init_session:
                        reader.init_session()
                        init_session = False

                    reader._check_update()
                    if pre_sleep_logic.is_set():
                        pre_sleep_logic.clear()
                else:
                    return


@manager_office(head_of_office=False)
def run_logic(
    logic_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    reader = LogicAgent.resolve_reader(kwargs["manager"])
    agent = LogicAgent(
        kwargs["manager"],
        reader=reader,
        pre_sleep_logic=logic_event,
        general_event=general_event,
    )
    agent.run_logic_engine()
