from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final

from loguru import logger

import imprint.configs as cfg
from imprint._core.configs import Coin as _Coin
from imprint._core.configs import Configuration as _Cfg
from imprint._core.configs import Setup as _Setup
from imprint._core.utils.exc_dumper import error_handler


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

    symbol: str
    strategy: cfg.Strategy
    execution: type[cfg.ExecutionEngine]

    with_execution: bool

    _coin: _Coin = field(init=False)
    _setup_core: _Setup = field(init=False)
    _account: cfg.Account = field(init=False)
    _init_complete: bool = field(init=False)
    _args: list[_Cfg] = field(init=False)
    _kwargs: dict[str, _Cfg] = field(init=False)

    @final
    def __post_init__(self) -> None:
        """Initialize logger, build configuration objects, and execute subclass post-initialization.

        Raises
        ------
        Exception
            Propagates any unhandled exception encountered during core execution or initialization.
        """

        logger.info(f"Initialization {self.__class__.__name__} mode, started.")

        self._args = [self.strategy.risk_management, self.strategy.footprint]
        self._coin = _Coin(symbol=self.symbol)
        self._setup_core = _Setup(
            algorithm_module=self.strategy.algorithm.__module__,
            algorithm_class_name=self.strategy.algorithm.__name__,
        )

        if self.with_execution:
            self._setup_core.execution = True
            self._setup_core.execution_module = self.execution.__module__
            self._setup_core.execution_class_name = self.execution.__name__
        else:
            self._setup_core.execution = False

        self._init_complete = self._post_init()

        logger.info(
            f"Init, {'completed' if self._init_complete else 'failed'}.\n"
        )
        self._args.append(self._coin)
        self._args.append(self._account)
        self._args.append(self._setup_core)

        self._kwargs = {}
        for obj in self._args:
            self._kwargs[obj.__class__.__name__] = obj

    @abstractmethod
    def _post_init(self) -> bool:
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
