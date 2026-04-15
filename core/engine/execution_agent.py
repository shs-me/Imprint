import gc
from multiprocessing.synchronize import Event

from .. import AgentManager, manager_office
from .. import StatusCodes as sc


class ExecutionAgent:
    def __init__(self, execution_event: Event, manager: AgentManager) -> None:
        self.manager, self.get_signal = manager, execution_event

        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem

    def run_execution_engine(self) -> None:
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        set_status, have_problem = self.set_status, self.have_problem
        have_task = self.have_task
        get_signal = self.get_signal
        while True:
            gc.collect()
            while True:
                set_status(code=SLEEP)
                if have_problem() is False:
                    if have_task():
                        break

                    if get_signal.is_set() is False:
                        get_signal.wait()

                    set_status(code=WAKE_UP)
                    # - - -
                    #
                    if get_signal.is_set():
                        get_signal.clear()

                else:
                    return


@manager_office()
def run_execution(execution_event: Event, **kwargs):
    agent = ExecutionAgent(execution_event=execution_event, manager=kwargs["manager"])
    agent.run_execution_engine()
