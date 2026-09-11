import importlib
from multiprocessing.synchronize import Event, Semaphore
from typing import Any

from imprint._core.ipc import NodeManager, supervisor
from imprint._core.pipeline.executing.router import Router as BaseExecution

__all__ = ["BaseExecution", "run_executing"]


@supervisor()
def run_executing(
    execution_event: Event, wss_sem: Semaphore, **kwargs: Any
) -> None:
    manager: NodeManager = kwargs["manager"]

    m_name = manager.cfgSetup.execution_module
    c_name = manager.cfgSetup.execution_class_name

    execution: type[BaseExecution] = getattr(
        importlib.import_module(m_name), c_name
    )
    manager.set_log(f"{execution.__name__} used as BaseExecution")
    agent = execution(
        _manager=manager, _execution_event=execution_event, _wss_sem=wss_sem
    )
    agent._executer.run()
