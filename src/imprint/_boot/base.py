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
    symbol: str
    strategy: cfg.Strategy
    execution: type[cfg.ExecutionEngine]

    with_execution: bool

    _coin: _Coin = field(init=False)
    _setup_core: _Setup = field(init=False)
    _account: cfg.Account = field(init=False)
    _init_complete: bool = field(init=False)
    _prefix_core_log_format: str = field(init=False)
    _args: list[_Cfg] = field(init=False)
    _kwargs: dict[str, _Cfg] = field(init=False)

    @final
    def __post_init__(self) -> None:
        self.__init_logger()

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

    @final
    def __init_logger(self) -> None:

        import imprint._boot as iboot
        import imprint._core as icore
        import imprint._vis as ivis
        from imprint._core.constant import (
            API_LOG_PATH,
            CORE_LOG_PATH,
            VISUALIZATION_LOG_PATH,
        )

        logger.remove()
        logger.add(
            API_LOG_PATH,
            format="{time:YY:MM:DD-HH:mm:ss} | {level} | Imprint | {message}",
            filter=lambda r: r["name"].startswith(iboot.__name__),  # pyright: ignore[reportOptionalMemberAccess]
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )
        logger.add(
            CORE_LOG_PATH,
            format=(
                self._prefix_core_log_format
                + "{extra[time]} | {extra[level]} | {extra[proc_name]} | {message}"
            ),
            filter=lambda r: r["name"].startswith(icore.__name__),  # pyright: ignore[reportOptionalMemberAccess]
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )
        logger.add(
            VISUALIZATION_LOG_PATH,
            format="{time:YY:MM:DD-HH:mm:ss} | {level} | {message}",
            filter=lambda r: r["name"].startswith(ivis.__name__),  # pyright: ignore[reportOptionalMemberAccess]
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )

    @abstractmethod
    def _post_init(self) -> bool: ...

    @final
    @error_handler()
    def run_core(self) -> None:
        if self._init_complete:
            from imprint._core.main import run

            logger.info("Core, started.")
            run(**self._kwargs)
            logger.info("Core, closed.\n")
