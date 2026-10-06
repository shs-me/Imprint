from multiprocessing.synchronize import Event
from typing import Any

from imprint._core.ipc import NodeManager, supervisor
from imprint._core.pipeline.engine.router import EngineRouter

__all__ = ["run_engine"]


@supervisor()
def run_engine(
    engine_event: Event, execution_event: Event, **kwargs: Any
) -> None:
    """Run the strategy engine process loop.

    Dynamic module loading constructs either a live or backtesting strategy engine
    and its matching orchestration agent based on configuration. Blocks and runs
    the agent's event loop until completion.

    Parameters
    ----------
    engine_event : multiprocessing.synchronize.Event
        Process synchronization event used to coordinate engine lifecycle and tick transitions.
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

    router: EngineRouter = EngineRouter(
        manager=manager,
        engine_event=engine_event,
        execution_event=execution_event,
    )
    router.run()
