from multiprocessing.synchronize import Event

from ...footprint import BaseFootprintWriter
from ...ipc import NodeManager, supervisor
from ...settings import ParsingProc

__all__ = ["run_parsing"]


@supervisor()
def run_parsing(
    parsing_event: Event,
    logic_event: Event,
    proc: ParsingProc = ParsingProc(),
    **kwargs,
) -> None:
    manager: NodeManager = kwargs["manager"]
    writer = BaseFootprintWriter(kwargs["manager"])
    if manager.cfgSetup.backtesting:
        from .backtest import Backtest as BacktestAgent

        agent = BacktestAgent(kwargs["manager"], writer)
    else:
        from .live import Live as LiveAgent

        agent = LiveAgent(kwargs["manager"], writer, parsing_event, logic_event)
    agent.run_parsing_engine()
