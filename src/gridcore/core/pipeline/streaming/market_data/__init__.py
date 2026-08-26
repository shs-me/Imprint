from multiprocessing.synchronize import Event

from ....ipc import NodeManager, supervisor
from ....settings import DataStreamProc

__all__ = ["run_market_data_stream"]


@supervisor()
def run_market_data_stream(
    engine_event: Event,
    proc: DataStreamProc = DataStreamProc(),
    **kwargs,
) -> None:
    manager: NodeManager = kwargs["manager"]

    if manager.cfgSetup.backtesting:
        from .backtest import Backtest as BacktestAgent

        agent = BacktestAgent(manager)
        agent.run_wss_engine()
    else:
        import asyncio

        from .live import Live as LiveAgent

        agent = LiveAgent(manager, engine_event)
        asyncio.run(agent.run_wss__engine())
