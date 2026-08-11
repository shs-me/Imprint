from multiprocessing.synchronize import Event

from ...ipc import NodeManager, supervisor
from ...settings import DataStreamProc

__all__ = ["run_streaming"]


@supervisor()
def run_streaming(
    parsing_event: Event,
    proc: DataStreamProc = DataStreamProc(),
    **kwargs,
) -> None:
    manager: NodeManager = kwargs["manager"]

    if manager.cfgSetup.backtesting:
        from .market_data.backtest import Backtest as BacktestAgent

        agent = BacktestAgent(manager=manager)
        agent.run_wss_engine()
    else:
        import asyncio

        from .market_data.live import Live as LiveAgent

        agent = LiveAgent(manager=manager, parsing_event=parsing_event)
        asyncio.run(agent.run_wss__engine())
