from typing import final, overload

import imprint.configs as cfg
from imprint._boot.backtest import BacktestEngine
from imprint._boot.live import Live as LiveEngine

RUN_MODES = cfg.Backtest | cfg.Live


@final
class Imprint:
    @overload
    def __new__(
        cls,
        run_mode: cfg.Backtest
        | tuple[type[cfg.Backtest], cfg.Backtest, cfg.Live],
        symbol: str,
        strategy: cfg.Strategy,
        execution: type[cfg.ExecutionEngine],
        with_execution: bool,
    ) -> BacktestEngine: ...
    @overload
    def __new__(
        cls,
        run_mode: cfg.Live | tuple[type[cfg.Live], cfg.Backtest, cfg.Live],
        symbol: str,
        strategy: cfg.Strategy,
        execution: type[cfg.ExecutionEngine],
        with_execution: bool,
    ) -> LiveEngine: ...
    def __new__(
        cls,
        run_mode: RUN_MODES | tuple[type[RUN_MODES], cfg.Backtest, cfg.Live],
        symbol: str,
        strategy: cfg.Strategy,
        execution: type[cfg.ExecutionEngine],
        with_execution: bool,
    ):
        if isinstance(run_mode, tuple):
            if run_mode[0] is cfg.Backtest:
                engine, mode = BacktestEngine, run_mode[1]
            else:
                engine, mode = LiveEngine, run_mode[2]
        else:
            if isinstance(run_mode, cfg.Backtest):
                engine, mode = BacktestEngine, run_mode
            else:
                engine, mode = LiveEngine, run_mode

        return engine(
            run_mode=mode,  # pyright: ignore[reportArgumentType]
            symbol=symbol,
            strategy=strategy,
            execution=execution,
            with_execution=with_execution,
        )
