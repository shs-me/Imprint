import importlib
from multiprocessing.synchronize import Event, Semaphore
from typing import Any

from imprint._core.ipc import NodeManager, supervisor
from imprint._core.pipeline.executing.router import ExecutionEngine

__all__ = [
    "ExecutionEngine",
    "run_executing",
]


@supervisor()
def run_executing(
    execution_event: Event, wss_sem: Semaphore, **kwargs: Any
) -> None:
    """Run the order execution process loop.

    Dynamically imports and configures the execution engine class, instantiates its
    underlying coordinator agent, and runs the main execution worker loop to process orders.

    Parameters
    ----------
    execution_event : multiprocessing.synchronize.Event
        Process synchronization event used to signal status changes and order triggers
        between the strategy engine and execution engine.
    wss_sem : multiprocessing.synchronize.Semaphore
        Semaphore regulating access and rate limits to connection resources of the WebSockets stream.
    **kwargs : dict[str, Any]
        Keyword arguments passed by the supervisor decorator. Must contain:

        manager : imprint._core.ipc.NodeManager
            IPC and configuration coordinator managing process memory nodes.

    Raises
    ------
    KeyError
        If ``'manager'`` is missing from ``kwargs``.
    AttributeError
        If the specified ``execution_class_name`` is not found in the resolved module.
    ModuleNotFoundError
        If the configured ``execution_module`` cannot be imported.
    """
    manager: NodeManager = kwargs["manager"]

    m_name = manager.cfgSetup.execution_module
    c_name = manager.cfgSetup.execution_class_name

    execution: type[ExecutionEngine] = getattr(
        importlib.import_module(m_name), c_name
    )
    agent = execution(
        _manager=manager, _execution_event=execution_event, _wss_sem=wss_sem
    )
    manager.set_log(f"{execution.__name__} used as ExecutionEngine")
    agent._executer.run()
