import importlib.util
import inspect
import os
import time
from multiprocessing.synchronize import Event, Lock

from core.constant import PLUGIN_PATH
from core.engine.analytical_tools.footprint.footprint_reader import FootprintReader
from core.engine.example import BaseFootprintReader
from core.settings import BacktestingMode as bm
from core.utils.handlers import error_handler
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office
from core.utils.monitoring.status_codes import StatusCodes as scs


class LogicAgent:
    def __init__(
        self,
        manager: AgentManager,
        reader: FootprintReader,
        pre_sleep_logic: Lock,
        general_event: Event,
    ) -> None:
        self.manager: AgentManager = manager
        self.reader: FootprintReader = reader
        self.pre_sleep_logic: Lock = pre_sleep_logic
        self.wait_main: Event = general_event

        self.set_proc_sc = manager.set_proc_sc
        self.check_task = manager.check_task
        self.task_status: memoryview = manager.task_status
        self.proc_status: memoryview = manager.proc_status

        self.backtesting: bool = manager.backtesting
        self.btMode: bm = manager.mode

    @error_handler(set_status_code=True)
    def run_logic_engine(self) -> None:
        # LocalLinks
        reader = self.reader
        pre_sleep_logic, alarm_clock = self.pre_sleep_logic, self._alarm_clock
        # - - -
        proc_status, task_status = self.proc_status, self.task_status
        # - - -
        while True:
            init_session = True
            while True:
                if proc_status[0] != 0 or task_status[0] != 0:
                    if task := self.check_task(complete=reader.spare_flag[0] == 0):
                        return
                    elif task & scs.FP_RE_INIT:
                        reader.dump_footprint()
                        break
                    elif task is False:
                        pass

                alarm_clock(task_status, pre_sleep_logic)
                if init_session:
                    reader.init_session()
                    init_session = False

                reader.check_update()

    def _alarm_clock(self, task_status: memoryview, pre_sleep_logic: Lock) -> None:
        mode, ZeroSleep, flag = self.btMode, bm.ZERO_SLEEP, self.reader.spare_flag
        if self.backtesting:
            if mode == bm.NONE_STOP or mode == ZeroSleep:
                flag[0] = 0
                while flag[0] == 0 and task_status[0] == 0:
                    if mode == ZeroSleep:
                        time.sleep(0)

                return

        flag[0] = 0
        pre_sleep_logic.acquire()


def resolve_reader(manager: AgentManager, execution_event: Event):
    paths = []
    for p in os.listdir(PLUGIN_PATH):
        if p.endswith(".py"):
            paths.append(f"{PLUGIN_PATH}/{p}")

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
