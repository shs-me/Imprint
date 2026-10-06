from multiprocessing.synchronize import Event, Semaphore
from typing import Any

from imprint._core.ipc import NodeManager, supervisor
from imprint._core.pipeline.streaming.router import StreamingRouter

__all__ = ["run_streaming"]


@supervisor()
def run_streaming(
    engine_event: Event,
    wss_sem: Semaphore,
    execution_event: Event,
    **kwargs: Any,
) -> None:
    """Run the market and order data streaming process loop.

    Depending on configuration, launches either a synchronous backtesting data stream agent
    or an asynchronous live data stream agent.

    Parameters
    ----------
    engine_event : multiprocessing.synchronize.Event
        Process synchronization event used to coordinate engine lifecycle and tick transitions.
    wss_sem : multiprocessing.synchronize.Semaphore
        Semaphore regulating access and rate limits to connection resources of the WebSockets stream.
    execution_event : multiprocessing.synchronize.Event
        Process synchronization event used to signal status changes and order triggers
        between the strategy engine and execution engine.
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

    router: StreamingRouter = StreamingRouter(
        manager=manager,
        engine_event=engine_event,
        wss_sem=wss_sem,
        execution_event=execution_event,
    )
    router.run()
