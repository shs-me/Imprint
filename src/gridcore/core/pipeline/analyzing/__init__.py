import importlib
from multiprocessing.synchronize import Event

from ...footprint import BaseFootprintReader
from ...ipc import NodeManager, supervisor
from ...settings import LogicProc

__all__ = ["run_analyzing"]


@supervisor()
def run_analyzing(
    logic_event: Event,
    execution_event: Event,
    proc: LogicProc = LogicProc(),
    **kwargs,
) -> None:
    manager: NodeManager = kwargs["manager"]

    m_name: str = manager.cfgSetup.algorithm_module
    c_name: str = manager.cfgSetup.algorithm_class_name

    reader_type: type[BaseFootprintReader] = getattr(
        importlib.import_module(m_name), c_name
    )

    if manager.cfgSetup.backtesting:
        from .backtest import SyncViaSpinLock

        sync = SyncViaSpinLock(manager)
    else:
        from .live import SyncViaEvent

        sync = SyncViaEvent(manager, execution_event)

    reader: BaseFootprintReader = reader_type(manager, sync)
    manager.set_text(f"{reader.__class__.__name__} used as BaseFootprintReader")

    if manager.cfgSetup.backtesting:
        from .backtest import Backtest as BacktestAgent

        agent = BacktestAgent(manager, reader)
    else:
        from .live import Live as LiveAgent

        agent = LiveAgent(manager, reader, logic_event)

    agent.run_logic_engine()
