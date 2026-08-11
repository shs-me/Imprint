from multiprocessing.synchronize import Event

from ....ipc import NodeManager, supervisor
from ....settings import DataStreamProc

__all__ = ["run_market_data_stream"]


@supervisor()
def run_market_data_stream(
    parsing_event: Event,
    proc: DataStreamProc = DataStreamProc(),
    **kwargs,
) -> None:
    manager: NodeManager = kwargs["manager"]

    if manager.cfgSetup.backtesting:
        from .backtest import Backtest as BacktestAgent

        agent = BacktestAgent(manager=kwargs["manager"])
        agent.run_wss_engine()
    else:
        import asyncio

        from .live import Live as LiveAgent

        agent = LiveAgent(manager=kwargs["manager"], parsing_event=parsing_event)
        asyncio.run(agent.run_wss__engine())
