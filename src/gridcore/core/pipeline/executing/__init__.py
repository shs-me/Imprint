import importlib
from multiprocessing.synchronize import Event
from typing import Any

from ...ipc import NodeManager, supervisor
from .router import Router as BaseExecution

__all__ = ["run_executing", "BaseExecution"]


@supervisor()
def run_executing(execution_event: Event, **kwargs: Any) -> None:
    manager: NodeManager = kwargs["manager"]

    m_name = manager.cfgSetup.execution_module
    c_name = manager.cfgSetup.execution_class_name

    execution: type[BaseExecution] = getattr(importlib.import_module(m_name), c_name)
    manager.set_text(f"{execution.__name__} used as BaseExecution")
    agent = execution(manager, execution_event=execution_event)
    agent._run_execution_engine()
