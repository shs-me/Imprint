import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import final

from imprint._core.footprint import (
    FootprintEngine,
    StrategyEngine,
    SyncWithExecution,
)
from imprint._core.ipc import NodeManager


@final
@dataclass(slots=True)
class EngineRouter:
    manager: NodeManager
    engine_event: Event
    execution_event: Event

    is_backtest: bool = field(init=False)
    sync: SyncWithExecution = field(init=False)

    def __post_init__(self) -> None:
        self.is_backtest = self.manager.cfgSetup.backtesting
        if self.is_backtest:
            from imprint._core.pipeline.engine.backtest import SyncViaSpinLock

            self.sync = SyncViaSpinLock(manager=self.manager)
        else:
            from imprint._core.pipeline.engine.live import SyncViaEvent

            self.sync = SyncViaEvent(
                manager=self.manager, execution_event=self.execution_event
            )

    @property
    def strategy_type(self) -> type[StrategyEngine]:
        m_name: str = self.manager.cfgSetup.algorithm_module
        c_name: str = self.manager.cfgSetup.algorithm_class_name
        return getattr(importlib.import_module(m_name), c_name)

    def run(self) -> None:
        strategy: StrategyEngine = self.strategy_type(
            _sync=self.sync, is_backtest=self.is_backtest
        )
        engine: FootprintEngine = FootprintEngine(
            manager=self.manager, strategy=strategy
        )
        if self.is_backtest:
            from imprint._core.pipeline.engine.backtest import (
                Backtest as BacktestAgent,
            )

            agent = BacktestAgent(
                manager=self.manager, strategy=strategy, engine=engine
            )
        else:
            from imprint._core.pipeline.engine.live import Live as LiveAgent

            agent = LiveAgent(
                manager=self.manager,
                strategy=strategy,
                engine=engine,
                engine_event=self.engine_event,
            )

        self.manager.set_log(
            f"{strategy.__class__.__name__} used as StrategyEngine"
        )
        agent.run()
