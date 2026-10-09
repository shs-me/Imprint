from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import final

from imprint._core.footprint import SyncWithExecution
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

    def run(self) -> None:
        if self.is_backtest:
            from imprint._core.pipeline.engine.backtest import (
                Backtest as BacktestAgent,
            )

            agent = BacktestAgent(manager=self.manager, sync=self.sync)
        else:
            from imprint._core.pipeline.engine.live import Live as LiveAgent

            agent = LiveAgent(
                manager=self.manager,
                sync=self.sync,
                engine_event=self.engine_event,
            )

        agent.run()
