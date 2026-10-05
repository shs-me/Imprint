from typing import final, overload

import imprint.configs as cfg
from imprint._boot.backtest import BacktestEngine
from imprint._boot.live import Live as LiveEngine

RUN_MODES = cfg.Backtest | cfg.Live


@final
class Imprint:
    """Route instantiation to either BacktestEngine or LiveEngine based on the provided run mode configuration."""

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
        """Initialize and return a concrete BacktestEngine or LiveEngine instance.

        Parameters
        ----------
        run_mode : imprint.configs.Backtest | imprint.configs.Live | tuple[type[imprint.configs.Backtest | imprint.configs.Live], imprint.configs.Backtest, imprint.configs.Live]
            Run mode configuration object or a tuple containing active engine type and configurations.
        symbol : str
            Target trading pair symbol (e.g., ``"BTCUSDT"``).
        strategy : imprint.configs.Strategy
            Trading strategy configuration containing algorithm, risk management, and footprint parameters.
        execution : type[imprint.configs.ExecutionEngine]
            Execution engine class handling order routing and position management.
        with_execution : bool
            Flag indicating whether execution is enabled.

        Returns
        -------
        BacktestEngine | LiveEngine
            Instantiated concrete engine corresponding to the selected run mode.
        """
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
