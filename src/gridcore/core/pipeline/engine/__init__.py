import importlib
from multiprocessing.synchronize import Event

from ...footprint import FootprintEngine
from ...ipc import NodeManager, supervisor
from ...settings import EngineProc

__all__ = ["run_engine"]


@supervisor()
def run_engine(
    engine_event: Event,
    execution_event: Event,
    proc: EngineProc = EngineProc(),
    **kwargs,
) -> None:
    manager: NodeManager = kwargs["manager"]

    m_name: str = manager.cfgSetup.algorithm_module
    c_name: str = manager.cfgSetup.algorithm_class_name

    engine_type: type[FootprintEngine] = getattr(
        importlib.import_module(m_name), c_name
    )

    if manager.cfgSetup.backtesting:
        from .backtest import SyncViaSpinLock

        sync = SyncViaSpinLock(manager)
    else:
        from .live import SyncViaEvent

        sync = SyncViaEvent(manager, execution_event)

    engine: FootprintEngine = engine_type(manager, sync)
    manager.set_text(f"{engine.__class__.__name__} used as FootprintEngine")

    if manager.cfgSetup.backtesting:
        from .backtest import Backtest as BacktestAgent

        agent = BacktestAgent(manager, engine)
    else:
        from .live import Live as LiveAgent

        agent = LiveAgent(manager, engine, engine_event)

    agent.run_engine()
