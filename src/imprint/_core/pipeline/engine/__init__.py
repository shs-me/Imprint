import importlib
from multiprocessing.synchronize import Event
from typing import Any

from imprint._core.footprint import StrategyEngine
from imprint._core.ipc import NodeManager, supervisor

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
    AttributeError
        If the specified ``algorithm_class_name`` is not found in the resolved module.
    ModuleNotFoundError
        If the configured ``algorithm_module`` cannot be imported.
    """
    manager: NodeManager = kwargs["manager"]

    m_name: str = manager.cfgSetup.algorithm_module
    c_name: str = manager.cfgSetup.algorithm_class_name

    engine_type: type[StrategyEngine] = getattr(
        importlib.import_module(m_name), c_name
    )

    if manager.cfgSetup.backtesting:
        from imprint._core.pipeline.engine.backtest import SyncViaSpinLock

        sync = SyncViaSpinLock(manager=manager)
    else:
        from imprint._core.pipeline.engine.live import SyncViaEvent

        sync = SyncViaEvent(manager=manager, execution_event=execution_event)

    engine: StrategyEngine = engine_type(manager, sync)

    if manager.cfgSetup.backtesting:
        from imprint._core.pipeline.engine.backtest import (
            Backtest as BacktestAgent,
        )

        agent = BacktestAgent(manager=manager, algorithm=engine)
    else:
        from imprint._core.pipeline.engine.live import Live as LiveAgent

        agent = LiveAgent(
            manager=manager, algorithm=engine, engine_event=engine_event
        )

    manager.set_log(f"{engine.__class__.__name__} used as StrategyEngine")
    agent.run()
