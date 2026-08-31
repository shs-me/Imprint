from multiprocessing.synchronize import Event, Semaphore
from typing import Any

from ...ipc import NodeManager, supervisor

__all__ = ["run_streaming"]


@supervisor()
def run_streaming(
    engine_event: Event,
    wss_sem: Semaphore,
    execution_event: Event,
    **kwargs: Any,
) -> None:
    manager: NodeManager = kwargs["manager"]

    if manager.cfgSetup.backtesting:
        from .backtest import BacktestAgent

        agent = BacktestAgent(manager=manager)
        agent.run()
    else:
        import asyncio

        from .live import LiveAgent

        agent = LiveAgent(manager, engine_event, execution_event, wss_sem)
        asyncio.run(agent.run_streams())
