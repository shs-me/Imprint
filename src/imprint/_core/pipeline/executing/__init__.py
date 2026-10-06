from multiprocessing.synchronize import Event, Semaphore
from typing import Any

from imprint._core.ipc import NodeManager, supervisor
from imprint._core.pipeline.executing.router import ExecutingRouter
from imprint._core.pipeline.executing.strategy import ExecutionEngine

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
    """
    manager: NodeManager = kwargs["manager"]

    router: ExecutingRouter = ExecutingRouter(
        manager=manager,
        execution_event=execution_event,
        wss_sem=wss_sem,
    )
    router.run()
