import gc
import importlib.util
import inspect
import os
import time
from multiprocessing.synchronize import Event, Lock

from .. import AgentManager, CorePath, error_handler, manager_office
from .. import StatusCodes as sc
from ..settings import BacktestingMode as bm
from . import BaseFootprintReader, FootprintReader


class LogicAgent:
    def __init__(
        self,
        manager: AgentManager,
        reader: FootprintReader,
        pre_sleep_logic: Lock,
        general_event: Event,
    ) -> None:
        self.manager, self.reader = manager, reader
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.pre_sleep_logic, self.wait_main = pre_sleep_logic, general_event
        self.mode = manager.cfgBacktesting.mode

    @error_handler(set_status_code=True)
    def run_logic_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        set_status, have_problem = self.set_status, self.have_problem
        status_task = self.manager.status_task
        pre_sleep_logic, alarm_clock = self.pre_sleep_logic, self._alarm_clock
        reader, have_task = self.reader, self.have_task
        #  - - -
        while True:
            gc.collect()
            self.wait_main.wait()
            init_session = True
            while True:
                set_status(code=SLEEP)
                alarm_clock(status_task, pre_sleep_logic)
                if have_problem() is False:
                    if have_task():
                        # if status_task[0] == sc.COMPLETE:
                        #    self.reader._save_array()
                        break

                    set_status(code=WAKE_UP)
                    if init_session:
                        reader.init_session()
                        init_session = False

                    reader.check_update()

                else:
                    return

    def _alarm_clock(self, status_task: memoryview, pre_sleep_logic: Lock) -> None:
        flag = self.reader.spare_flag
        flag[0] = 0
        if self.mode == bm.REAL_TIME_SIM:
            pre_sleep_logic.acquire()

        elif self.mode == bm.NONE_STOP:
            while flag[0] == 0 and status_task[0] == 0:
                pass

        elif self.mode == bm.ZERO_SLEEP:
            while flag[0] == 0 and status_task[0] == 0:
                time.sleep(0)


def resolve_reader(manager: AgentManager, execution_event: Event):
    paths = []
    for p in os.listdir(CorePath.plugins_dir):
        if p.endswith(".py"):
            paths.append(f"{CorePath.plugins_dir}/{p}")

    for path in paths:
        result = get_plugin(path, manager, execution_event)
        if result:
            return result

    return BaseFootprintReader(manager=manager, execution_event=execution_event)


@error_handler()
def get_plugin(path: str, manager: AgentManager, execution_event: Event):
    module_name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is not None and spec.loader is not None:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, FootprintReader):
                if obj is not FootprintReader:
                    return obj(manager=manager, execution_event=execution_event)


@manager_office()
def run_logic(
    logic_lock: Lock,
    execution_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    reader = resolve_reader(kwargs["manager"], execution_event)
    agent = LogicAgent(
        kwargs["manager"],
        reader=reader,
        pre_sleep_logic=logic_lock,
        general_event=general_event,
    )
    agent.run_logic_engine()
