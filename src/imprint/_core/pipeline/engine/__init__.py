import importlib
from multiprocessing.synchronize import Event
from typing import Any

from imprint._core.footprint import FootprintEngine
from imprint._core.ipc import NodeManager, supervisor

__all__ = ["run_engine"]


@supervisor()
def run_engine(
    engine_event: Event, execution_event: Event, **kwargs: Any
) -> None:
    manager: NodeManager = kwargs["manager"]

    m_name: str = manager.cfgSetup.algorithm_module
    c_name: str = manager.cfgSetup.algorithm_class_name

    engine_type: type[FootprintEngine] = getattr(
        importlib.import_module(m_name), c_name
    )

    if manager.cfgSetup.backtesting:
        from imprint._core.pipeline.engine.backtest import SyncViaSpinLock

        sync = SyncViaSpinLock(manager)
    else:
        from imprint._core.pipeline.engine.live import SyncViaEvent

        sync = SyncViaEvent(manager, execution_event)

    engine: FootprintEngine = engine_type(manager, sync)
    manager.set_log(f"{engine.__class__.__name__} used as FootprintEngine")

    if manager.cfgSetup.backtesting:
        from imprint._core.pipeline.engine.backtest import (
            Backtest as BacktestAgent,
        )

        agent = BacktestAgent(manager, engine)
    else:
        from imprint._core.pipeline.engine.live import Live as LiveAgent

        agent = LiveAgent(manager, engine, engine_event)

    agent.run()
