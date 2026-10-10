"""Provide abstract base engine orchestration and builder binding utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import Any, TypeVar, final

from loguru import logger

from imprint._boot.configs import FootprintBatch, RiskManagementBatch
from imprint._core.configs import (
    Configuration,
    Footprint,
    Percent,
    RiskManagement,
    Setup,
    SharedMemorySegments,
)
from imprint._core.footprint import StrategyEngine
from imprint._core.pipeline.executing import ExecutionEngine
from imprint._core.settings import KwgsKeys, Timeframe
from imprint._core.utils.exc_dumper import error_handler

T = TypeVar("T")


class InitFailed(Exception):
    """Raised when engine initialization fails."""


class EngineNotBuilded(Exception):
    """Raised when attempting to access an engine before build() is called."""


@dataclass(slots=True)
class Base(ABC):
    """Provide common initialization, configuration mapping, and lifecycle management for trading engines.

    Parameters
    ----------
    _algorithm : type[StrategyEngine] | list[type[StrategyEngine]]
        Strategy algorithm class or sequence of classes.
    _execution : type[ExecutionEngine] | list[type[ExecutionEngine]]
        Execution engine class or sequence of classes.
    _footprint : Footprint | FootprintBatch
        Footprint configuration or batch specification.
    _risk_management : RiskManagement | RiskManagementBatch
        Risk management configuration or batch specification.
    _with_execution : bool
        Whether to enable live order execution and management.

    Attributes
    ----------
    _setups : list[Setup]
        Compiled sequence of strategy execution setups.
    _footprints : list[Footprint]
        Compiled sequence of footprint configurations.
    _risk_managements : list[RiskManagement]
        Compiled sequence of risk management configurations.
    _other_configs : list[Sequence[Configuration]]
        Additional auxiliary configuration sequences.
    _segments : list[SharedMemorySegments]
        Shared memory IPC segment descriptors.
    _configs : list[list[Configuration]]
        Aggregated configuration matrices grouped per engine instance.
    _kwargs : dict[str, list[list[Configuration]] | SharedMemorySegments]
        Keyword arguments payload passed to the core execution process.
    _init_complete : bool
        Flag indicating whether initialization completed successfully.
    """

    _algorithm: type[StrategyEngine] | list[type[StrategyEngine]]
    _execution: type[ExecutionEngine] | list[type[ExecutionEngine]]
    _footprint: Footprint | FootprintBatch
    _risk_management: RiskManagement | RiskManagementBatch
    _with_execution: bool

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
        """Initialize engine configurations, build setup lists, and prepare shared memory payloads."""
        logger.info(f"Initialization {self.__class__.__name__} mode, started.")

        self._setups = []
        self._footprints = []
        self._risk_managements = []
        self._other_configs = []
        self._segments = []
        self._configs = []
        self._kwargs = {}

        try:
            self._prepare_setup_config()
            self._prepare_fp_config()
            self._prepare_rm_config()
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

    def _prepare_setup_config(self) -> None:
        """Construct setup configurations for strategy algorithms and execution engines."""
        if not isinstance(self._algorithm, list) and not isinstance(
            self._execution, list
        ):
            self._setups.append(
                Setup(
                    algorithm_module=self._algorithm.__module__,
                    algorithm_class_name=self._algorithm.__name__,
                    execution_module=self._execution.__module__,
                    execution_class_name=self._execution.__name__,
                    execution=self._with_execution,
                )
            )
        else:
            algorithms = self._to_list(self._algorithm)
            executions = self._to_list(self._execution)

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

                setup.execution = self._with_execution

    @final
    def _prepare_fp_config(self) -> None:
        """Construct footprint configurations from singleton or batch specifications."""
        _ = self._footprint
        # - - -
        if isinstance(_, Footprint):
            self._footprints.append(_)
        else:
            for tf, cr, st, ws, wc in zip_longest(
                _.timeframe,
                _.chart_range,
                _.step_tick,
                _.state,
                _.ctrade,
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
    def _prepare_rm_config(self) -> None:
        """Construct risk management configurations from singleton or batch specifications."""
        _ = self._risk_management
        # - - -
        if isinstance(_, RiskManagement):
            self._risk_managements.append(_)
        else:
            for eq, mkb, msb, tp, sl, st, at in zip_longest(
                _.entry_qty,
                _.max_lock_balance,
                _.max_loss_balance,
                _.tp_dev,
                _.sl_dev,
                _.pass_execute_signal_if_timer_ms_exepired,
                _.pass_signal_if_analysis_time_big,
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
    def _post_init(self) -> None:
        """Perform subclass-specific post-initialization tasks and resource allocations."""

    def _to_list[T](self, obj: list[T] | T, /) -> list[T]:
        """Convert a single element or sequence into a list.

        Parameters
        ----------
        obj : list[T] | T
            Item or list of items to convert.

        Returns
        -------
        list[T]
            Standard Python list containing the items.
        """
        return list(obj) if isinstance(obj, list) else [obj]  # pyright: ignore[reportUnknownArgumentType]

    def _list_get[T](self, arr: list[T], index: int) -> T | None:
        """Safely retrieve an element from a list by index.

        Parameters
        ----------
        arr : list[T]
            Target list to index into.
        index : int
            Index position to access.

        Returns
        -------
        T | None
            Element at the specified index, or None if index is out of bounds.
        """
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


@final
class BoundFactory:
    """Bind configuration instantiation directly to a parent builder instance."""

    def __init__(
        self,
        config_cls: type[T],
        builder: Any,
        target_attr: str,
    ) -> None:
        """Initialize bound factory with configuration class, builder reference, and target attribute.

        Parameters
        ----------
        config_cls : type[T]
            The configuration dataclass type to instantiate.
        builder : Any
            The parent builder instance holding the configuration attribute.
        target_attr : str
            The attribute name on the builder to store the instantiated configuration.
        """
        self._config_cls = config_cls
        self._builder = builder
        self._target_attr = target_attr

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Instantiate the configuration class, assign it to the builder, and return the builder.

        Parameters
        ----------
        *args : Any
            Positional arguments passed to the configuration class constructor.
        **kwargs : Any
            Keyword arguments passed to the configuration class constructor.

        Returns
        -------
        Any
            The parent builder instance for method chaining.
        """
        instance = self._config_cls(*args, **kwargs)
        setattr(self._builder, self._target_attr, instance)
        return self._builder
