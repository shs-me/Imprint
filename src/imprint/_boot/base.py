from abc import ABC, abstractmethod
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import Any, final

from loguru import logger

import imprint.configs as cfg
from imprint._core.configs import (
    Coin,
    Configuration,
    Footprint,
    Setup,
    SharedMemorySegments,
)
from imprint._core.settings import KwgsKeys
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

    strategy: cfg.Strategy
    symbol: str | list[str]
    with_execution: bool

    _coins: list[Coin] = field(init=False)
    _setups: list[Setup] = field(init=False)
    _footprints: list[cfg.Footprint] = field(init=False)
    _risk_managements: list[cfg.RiskManagement] = field(init=False)
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

        self._coins = []
        self._setups = []
        self._footprints = []
        self._risk_managements = []
        self._other_configs = []
        self._segments = []
        self._configs = []
        self._kwargs = {}

        symbols: list[str] = self.to_list(self.symbol, "")
        algorithms: list[type[cfg.StrategyEngine]] = self.to_list(
            self.strategy.algorithm, cfg.StrategyEngine
        )
        executions: list[type[cfg.ExecutionEngine]] = self.to_list(
            self.strategy.execution, cfg.ExecutionEngine
        )
        footprints: list[Footprint] = self.to_list(
            self.strategy.footprint, cfg.Footprint()
        )
        risk_managements: list[cfg.RiskManagement] = self.to_list(
            self.strategy.risk_management, cfg.RiskManagement()
        )
        for sym, algo, exec, fp, rm in zip_longest(
            symbols,
            algorithms,
            executions,
            footprints,
            risk_managements,
            fillvalue=None,
        ):
            if sym:
                coin: Coin = (
                    deepcopy(self._coins[-1]) if self._coins else Coin()
                )
                coin.symbol = sym
                self._coins.append(coin)

            if algo or exec:
                setup: Setup = (
                    deepcopy(self._setups[-1]) if self._setups else Setup()
                )
                if algo:
                    setup.algorithm_module = algo.__module__
                    setup.algorithm_class_name = algo.__name__
                if exec:
                    setup.execution_module = exec.__module__
                    setup.execution_class_name = exec.__name__

                if self.with_execution:
                    setup.execution = True
                else:
                    setup.execution = False

                self._setups.append(setup)

            if fp:
                self._footprints.append(fp)

            if rm:
                self._risk_managements.append(rm)

        try:
            self._post_init()
        except InitFailed as e:
            return logger.info(f"Init, failed: {e}.\n")

        for configs in zip_longest(
            self._coins,
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

    def to_list[T](self, obj: Any, _response_type: T, /) -> list[T]:
        return list(obj) if isinstance(obj, (tuple, list)) else [obj]  # pyright: ignore[reportUnknownArgumentType]

    @abstractmethod
    def _post_init(self) -> None:
        """Execute mode-specific post-initialization routines and resource setup.

        Returns
        -------
        bool
            True if initialization succeeds; False otherwise.
        """

    @final
    @error_handler()
    def run_core(self) -> None:
        """Execute the core trading engine lifecycle if initialization completed successfully."""
        if self._init_complete:
            from imprint._core.main import run

            logger.info("Core, started.")
            run(**self._kwargs)
            logger.info("Core, closed.\n")
