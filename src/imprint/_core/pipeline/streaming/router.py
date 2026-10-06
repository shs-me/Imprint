from dataclasses import dataclass
from multiprocessing.synchronize import Event, Semaphore
from typing import final

from imprint._core.ipc import NodeManager


@final
@dataclass(slots=True)
class StreamingRouter:
    """Run the market and order data streaming process loop.

    Depending on configuration, launches either a synchronous backtesting data stream agent
    or an asynchronous live data stream agent.

    Parameters
    ----------
    engine_event : multiprocessing.synchronize.Event
        Process synchronization event used to coordinate engine lifecycle and tick transitions.
    wss_sem : multiprocessing.synchronize.Semaphore
        Semaphore regulating access and rate limits to connection resources of the WebSockets stream.
    execution_event : multiprocessing.synchronize.Event
        Process synchronization event used to signal status changes and order triggers
        between the strategy engine and execution engine.
    """

    manager: NodeManager
    engine_event: Event
    wss_sem: Semaphore
    execution_event: Event

    def run(self) -> None:
        if self.manager.cfgSetup.backtesting:
            from imprint._core.pipeline.streaming.backtest import BacktestAgent

            agent = BacktestAgent(manager=self.manager)
            agent.run()
        else:
            import asyncio

            from imprint._core.pipeline.streaming.live import LiveAgent

            agent = LiveAgent(
                manager=self.manager,
                engine_event=self.engine_event,
                execution_event=self.execution_event,
                wss_sem=self.wss_sem,
            )
            asyncio.run(agent.run_streams())
