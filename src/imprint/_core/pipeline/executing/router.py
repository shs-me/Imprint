import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event, Semaphore
from typing import final

from imprint._core.account import Account
from imprint._core.ipc import NodeManager
from imprint._core.pipeline.executing.backtest import Backtest as BacktestAgent
from imprint._core.pipeline.executing.live import Live as LiveAgent
from imprint._core.pipeline.executing.strategy import ExecutionEngine
from imprint._core.types import SendOrderMethodSignature


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

    is_backtesting: bool = field(init=False)
    count_open_positions: memoryview = field(init=False)
    account: Account = field(init=False)
    send_order: SendOrderMethodSignature = field(init=False)

    @property
    def execution_type(self) -> type[ExecutionEngine]:
        m_name = self.manager.cfgSetup.execution_module
        c_name = self.manager.cfgSetup.execution_class_name
        return getattr(importlib.import_module(m_name), c_name)

    def run(self) -> None:
        engine = self.execution_type()
        self.is_backtesting = self.manager.cfgSetup.backtesting

        if self.is_backtesting:
            agent = BacktestAgent(manager=self.manager, strategy=engine)
        else:
            agent = LiveAgent(
                manager=self.manager,
                strategy=engine,
                execution_event=self.execution_event,
                wss_sem=self.wss_sem,
            )

        engine.is_backtesting = self.is_backtesting
        engine.count_open_positions = agent.count_open_positions
        engine.account = agent.account
        engine.send_order = agent.send_order

        self.manager.set_log(
            f"{engine.__class__.__name__} used as ExecutionEngine"
        )
        agent.run()
