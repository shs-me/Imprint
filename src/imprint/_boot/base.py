from abc import ABC, abstractmethod
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import final

from loguru import logger

import imprint.configs as cfg
from imprint._core.configs import (
    Configuration,
    Footprint,
    Percent,
    RiskManagement,
    Setup,
    SharedMemorySegments,
)
from imprint._core.settings import KwgsKeys, Timeframe
from imprint._core.utils.exc_dumper import error_handler


class InitFailed(Exception): ...


@dataclass(slots=True)
class Base(ABC):
    """Provide common initialization, logging, and core execution lifecycle for trading run modes.

    Parameters
    ----------
    symbol : str
        Target trading pair symbol (e.g., ``"BTCUSDT"``).
    strategy : imprint.configs.Strategy
        Trading strategy configuration containing algorithm, risk management, and footprint parameters.
    execution : type[imprint.configs.ExecutionEngine]
        Execution engine class handling order routing and position management.
    with_execution : bool
        Flag indicating whether live/backtest execution is enabled.

    Attributes
    ----------
    symbol : str
        Target trading pair symbol.
    strategy : imprint.configs.Strategy
        Trading strategy configuration.
    execution : type[imprint.configs.ExecutionEngine]
        Execution engine class.
    with_execution : bool
        Flag indicating if execution is enabled.
    """

    strategy: cfg.Strategy | cfg.StrategyBatch
    with_execution: bool

    _setups: list[Setup] = field(init=False)
    _footprints: list[Footprint] = field(init=False)
    _risk_managements: list[RiskManagement] = field(init=False)
    _other_configs: list[Sequence[Configuration]] = field(init=False)

    _segments: list[SharedMemorySegments] = field(init=False)
    _configs: list[list[Configuration]] = field(init=False)
    _kwargs: dict[str, list[list[Configuration]] | SharedMemorySegments] = (
        field(init=False)
    )
    _init_complete: bool = field(init=False)

    @final
    def __post_init__(self) -> None:
        logger.info(f"Initialization {self.__class__.__name__} mode, started.")

        self._setups = []
        self._footprints = []
        self._risk_managements = []
        self._other_configs = []
        self._segments = []
        self._configs = []
        self._kwargs = {}

        try:
            self.prepare_setup_config()
            self.prepare_fp_config()
            self.prepare_rm_config()
            self._post_init()

        except InitFailed as e:
            return logger.info(f"Init, failed: {e}.\n")

        for configs in zip_longest(
            self._setups,
            self._footprints,
            self._risk_managements,
            *self._other_configs,
            fillvalue=None,
        ):
            self._configs.append(
                [config for config in configs if config is not None]
            )

        self._kwargs[KwgsKeys.Configs.name] = self._configs

        for obj in self._segments:
            self._kwargs[obj.__class__.__name__] = obj

        self._init_complete = True
        logger.info("Init, completed.\n")

    def prepare_setup_config(self) -> None:
        _ = self.strategy
        # - - -
        if isinstance(_, cfg.Strategy):
            self._setups.append(
                Setup(
                    algorithm_module=_.algorithm.__module__,
                    algorithm_class_name=_.algorithm.__name__,
                    execution_module=_.execution.__module__,
                    execution_class_name=_.execution.__name__,
                    execution=self.with_execution,
                )
            )
        else:
            algorithms = self.to_list(_.algorithm)
            executions = self.to_list(_.execution)

            for algo, exec in zip_longest(
                algorithms, executions, fillvalue=None
            ):
                setup: Setup = (
                    deepcopy(self._setups[-1]) if self._setups else Setup()
                )
                self._setups.append(setup)

                if algo is not None:
                    setup.algorithm_module = algo.__module__
                    setup.algorithm_class_name = algo.__name__
                if exec is not None:
                    setup.execution_module = exec.__module__
                    setup.execution_class_name = exec.__name__

                setup.execution = self.with_execution

    @final
    def prepare_fp_config(self) -> None:
        _ = self.strategy
        # - - -
        if isinstance(_, cfg.Strategy):
            self._footprints.append(_.footprint)
        else:
            timeframes = self.to_list(_.footprint.timeframe)
            chart_ranges = self.to_list(_.footprint.chart_range)
            step_ticks = self.to_list(_.footprint.step_tick)
            with_states = self.to_list(_.footprint.state)
            with_ctrades = self.to_list(_.footprint.ctrade)

            for tf, cr, st, ws, wc in zip_longest(
                timeframes,
                chart_ranges,
                step_ticks,
                with_states,
                with_ctrades,
                fillvalue=None,
            ):
                fp: Footprint = (
                    deepcopy(self._footprints[-1])
                    if self._footprints
                    else Footprint()
                )
                self._footprints.append(fp)

                if isinstance(tf, Timeframe):
                    fp.timeframe = tf
                if isinstance(cr, int):
                    fp.chart_range = cr
                if isinstance(st, int):
                    fp.step_tick = st
                if isinstance(ws, bool):
                    fp.state = ws
                if isinstance(wc, bool):
                    fp.ctrade = wc

    @final
    def prepare_rm_config(self) -> None:
        _ = self.strategy
        # - - -
        if isinstance(_, cfg.Strategy):
            self._risk_managements.append(_.risk_management)
        else:
            entry_qtys = self.to_list(_.risk_management.entry_qty)
            max_lock_balances = self.to_list(_.risk_management.max_lock_balance)
            max_loss_balances = self.to_list(_.risk_management.max_loss_balance)
            tp_devs = self.to_list(_.risk_management.tp_dev)
            sl_devs = self.to_list(_.risk_management.sl_dev)
            signal_timers = self.to_list(
                _.risk_management.pass_execute_signal_if_timer_ms_exepired
            )
            analyze_timers = self.to_list(
                _.risk_management.pass_signal_if_analysis_time_big
            )

            for eq, mkb, msb, tp, sl, st, at in zip_longest(
                entry_qtys,
                max_lock_balances,
                max_loss_balances,
                tp_devs,
                sl_devs,
                signal_timers,
                analyze_timers,
                fillvalue=None,
            ):
                rm: RiskManagement = (
                    deepcopy(self._risk_managements[-1])
                    if self._risk_managements
                    else RiskManagement()
                )
                self._risk_managements.append(rm)

                if isinstance(eq, Percent):
                    rm.entry_qty = eq
                if isinstance(mkb, Percent):
                    rm.max_lock_balance = mkb
                if isinstance(msb, Percent):
                    rm.max_loss_balance = msb
                if isinstance(tp, Percent):
                    rm.tp_dev = tp
                if isinstance(sl, Percent):
                    rm.sl_dev = sl
                if isinstance(st, int):
                    rm.pass_execute_signal_if_timer_ms_exepired = st
                if isinstance(at, int):
                    rm.pass_signal_if_analysis_time_big = at

    @abstractmethod
    def _post_init(self) -> None: ...

    def to_list[T](self, obj: list[T] | T, /) -> list[T]:
        return list(obj) if isinstance(obj, list) else [obj]  # pyright: ignore[reportUnknownArgumentType]

    def list_get[T](self, arr: list[T], index: int) -> T | None:
        try:
            return arr[index]
        except IndexError:
            return None

    @final
    @error_handler()
    def run_core(self) -> None:
        """Execute the core trading engine lifecycle if initialization completed successfully."""
        if self._init_complete:
            from imprint._core.main import run

            logger.info("Core, started.")
            run(**self._kwargs)
            logger.info("Core, closed.\n")
