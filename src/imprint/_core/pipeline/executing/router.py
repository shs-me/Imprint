from dataclasses import dataclass
from multiprocessing.synchronize import Event, Semaphore
from typing import final

from imprint._core.ipc import NodeManager
from imprint._core.pipeline.executing.backtest import Backtest as BacktestAgent
from imprint._core.pipeline.executing.live import Live as LiveAgent


@final
@dataclass(slots=True)
class ExecutingRouter:
    """Abstract router managing backtest and live execution agents.

    Routes execution events and states between a pipeline's node manager and the
    appropriate underlying backtest or live execution agent.

    Parameters
    ----------
    manager : NodeManager
        Process manager controlling the execution setup, configuration, and pipeline nodes.
    execution_event : multiprocessing.synchronize.Event
        Synchronization event signaling live execution state changes.
    wss_sem : multiprocessing.synchronize.Semaphore
        Semaphore regulating concurrent WebSockets connections and rate limits.
    """

    manager: NodeManager
    execution_event: Event
    wss_sem: Semaphore

    def run(self) -> None:
        is_backtesting = self.manager.cfgSetup.backtesting

        if is_backtesting:
            agent = BacktestAgent(manager=self.manager)
        else:
            agent = LiveAgent(
                manager=self.manager,
                execution_event=self.execution_event,
                wss_sem=self.wss_sem,
            )

        agent.run()
