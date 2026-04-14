import gc
import importlib.util
import inspect
import os
from multiprocessing.synchronize import Event

from .. import AgentManager, CorePath, error_handler, manager_office
from .. import StatusCodes as sc
from . import BaseFootprintReader, FootprintReader


class LogicAgent:
    def __init__(
        self,
        manager: AgentManager,
        reader: FootprintReader,
        pre_sleep_logic: Event,
        general_event: Event,
    ) -> None:
        self.manager, self.reader = manager, reader
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        self.pre_sleep_logic, self.wait_main = pre_sleep_logic, general_event

    def _alarm_clock(self, tts: memoryview) -> bool:
        counter = 1
        last_box = self.reader.last_box
        box_id = self.reader.flag_buf
        while last_box == box_id[0]:
            counter += 1
            if counter >= tts[0]:
                return True
        else:
            return False

    @error_handler(set_status_code=True)
    def run_logic_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        set_status, have_problem = self.set_status, self.have_problem
        tts_buf = self.manager.time_to_sleep_buf
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

                    if alarm_clock(tts_buf):
                        if pre_sleep_logic.is_set() is False:
                            pre_sleep_logic.wait()
                        continue

                    set_status(code=WAKE_UP)
                    if init_session:
                        reader.init_session()
                        init_session = False

                    reader.check_update()
                    if pre_sleep_logic.is_set():
                        pre_sleep_logic.clear()

                else:
                    return


def resolve_reader(manager: AgentManager):
    paths = []
    for p in os.listdir(CorePath.plugins_dir):
        if p.endswith(".py"):
            paths.append(f"{CorePath.plugins_dir}/{p}")

    for path in paths:
        result = get_plugin(path, manager)
        if result:
            return result

    return BaseFootprintReader(manager=manager)


@error_handler()
def get_plugin(path: str, manager: AgentManager):
    module_name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is not None and spec.loader is not None:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, FootprintReader):
                if obj is not FootprintReader:
                    return obj(manager=manager)


@manager_office()
def run_logic(
    logic_event: Event,
    general_event: Event,
    **kwargs,
) -> None:
    reader = resolve_reader(kwargs["manager"])
    agent = LogicAgent(
        kwargs["manager"],
        reader=reader,
        pre_sleep_logic=logic_event,
        general_event=general_event,
    )
    agent.run_logic_engine()
