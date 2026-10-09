from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import Any, TypeVar, final

from loguru import logger

from imprint._boot.configs import FootprintBatch, RiskManagementBatch
from imprint._core import constant as c
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


class InitFailed(Exception): ...


class EngineNotBuilded(Exception): ...


@dataclass(slots=True)
class Base(ABC):
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
        self._init_logger()

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

    def _init_logger(self) -> None:

        import imprint._boot as _iboot
        import imprint._core as _icore
        import imprint._vis as _ivis

        logger.remove()
        logger.add(
            c.API_LOG_PATH,
            format="{time:YY:MM:DD-HH:mm:ss} | {level} | Imprint | {message}",
            filter=lambda r: r["name"].startswith(_iboot.__name__),  # pyright: ignore[reportOptionalMemberAccess]
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )
        logger.add(
            c.CORE_LOG_PATH,
            format=(
                "{elapsed} | {extra[time]} | {extra[level]} | {extra[proc_name]} | {message}"
            ),
            filter=lambda r: r["name"].startswith(_icore.__name__),  # pyright: ignore[reportOptionalMemberAccess]
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )
        logger.add(
            c.VISUALIZATION_LOG_PATH,
            format="{time:YY:MM:DD-HH:mm:ss} | {level} | {message}",
            filter=lambda r: r["name"].startswith(_ivis.__name__),  # pyright: ignore[reportOptionalMemberAccess]
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )

    def _prepare_setup_config(self) -> None:
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
    def _post_init(self) -> None: ...

    def _to_list[T](self, obj: list[T] | T, /) -> list[T]:
        return list(obj) if isinstance(obj, list) else [obj]  # pyright: ignore[reportUnknownArgumentType]

    def _list_get[T](self, arr: list[T], index: int) -> T | None:
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
    def __init__(
        self,
        config_cls: type[T],
        builder: Any,
        target_attr: str,
    ) -> None:
        self._config_cls = config_cls
        self._builder = builder
        self._target_attr = target_attr

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        instance = self._config_cls(*args, **kwargs)
        setattr(self._builder, self._target_attr, instance)
        return self._builder
