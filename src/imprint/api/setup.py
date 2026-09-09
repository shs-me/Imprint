from dataclasses import dataclass, field
from typing import final

from loguru import logger

from imprint.core import constant
from imprint.core.configs import (
    Account,
    Connector,
    Footprint,
    RiskManagement,
    pct,
)
from imprint.core.configs import Coin as _Coin
from imprint.core.configs import Configuration as _Cfg
from imprint.core.configs import Setup as _Setup
from imprint.core.footprint import FootprintEngine
from imprint.core.pipeline.executing import BaseExecution
from imprint.core.settings import Timeframe
from imprint.core.utils import AggTradesDecoder, OrderEncoder, UserStreamDecoder
from imprint.core.utils.agg_trades_history_downloader import DownloadError
from imprint.core.utils.exc_dumper import error_handler

__all__ = [
    "Account",
    "AggTradesDecoder",
    "Backtest",
    "BaseExecution",
    "Connector",
    "Footprint",
    "FootprintEngine",
    "Imprint",
    "Live",
    "OrderEncoder",
    "RiskManagement",
    "Strategy",
    "Timeframe",
    "UserStreamDecoder",
    "constant",
    "pct",
]


@final
@dataclass(slots=True)
class Backtest:
    account: Account
    tick_size: str = "0.01"
    lot_size: str = "0.001"
    backtest_start_date: str = "2026-01-01"
    backtest_end_date: str = "2026-01-01"


@final
@dataclass(slots=True)
class Live:
    connector: Connector
    agg_trades_decoder: type[AggTradesDecoder]
    user_stream_decoder: type[UserStreamDecoder]
    order_encoder: type[OrderEncoder]


@final
@dataclass(slots=True)
class Strategy:
    algorithm: type[FootprintEngine]
    footprint: Footprint
    risk_management: RiskManagement


@final
@dataclass(slots=True)
class Imprint:
    run_mode: Backtest | Live | tuple[type[Backtest | Live], Backtest, Live]
    symbol: str
    strategy: Strategy
    execution: type[BaseExecution]

    with_execution: bool = field(default=False)

    __coin: _Coin = field(init=False)
    __setup_core: _Setup = field(init=False)
    __kwargs: dict[str, _Cfg] = field(default_factory=dict, init=False)
    __backtest: Backtest = field(init=False)
    __live: Live = field(init=False)

    def __post_init__(self) -> None:
        args: list[_Cfg] = [
            self.strategy.risk_management,
            self.strategy.footprint,
        ]
        self.__coin = _Coin(symbol=self.symbol)
        self.__setup_core = _Setup(
            algorithm_module=self.strategy.algorithm.__module__,
            algorithm_class_name=self.strategy.algorithm.__name__,
        )

        if self.is_backtest_mode:
            self.__backtest_setup()
            args.append(self.__backtest.account)
        else:
            self.__live_setup()
            args.append(self.__live.connector)

        args.append(self.__coin)

        if self.with_execution:
            self.__setup_core.execution = True
            self.__setup_core.execution_module = self.execution.__module__
            self.__setup_core.execution_class_name = self.execution.__name__
        else:
            self.__setup_core.execution = False

        args.append(self.__setup_core)

        for obj in args:
            self.__kwargs[obj.__class__.__name__] = obj

    @property
    def is_backtest_mode(self) -> bool:
        if (not hasattr(self, f"_{Imprint.__name__}__backtest")) and (
            not hasattr(self, f"_{Imprint.__name__}__live")
        ):
            if isinstance(self.run_mode, tuple):
                if self.run_mode[0] is Backtest:
                    self.__backtest = self.run_mode[1]
                else:
                    self.__live = self.run_mode[2]
            else:
                if isinstance(self.run_mode, Backtest):
                    self.__backtest = self.run_mode
                else:
                    self.__live = self.run_mode

        return hasattr(self, f"_{Imprint.__name__}__backtest")

    def __backtest_setup(self) -> None:
        self.__setup_core.backtest_start_date = (
            self.__backtest.backtest_start_date
        )
        self.__setup_core.backtest_end_date = self.__backtest.backtest_end_date
        self.__setup_core.backtesting = True

        self.__coin.tick_size = self.__backtest.tick_size
        self.__coin.lot_size = self.__backtest.lot_size

    def __live_setup(self) -> None:
        self.__setup_core.agg_trades_decoder_module = (
            self.__live.agg_trades_decoder.__module__
        )
        self.__setup_core.agg_trades_decoder_class_name = (
            self.__live.agg_trades_decoder.__name__
        )
        self.__setup_core.user_stream_decoder_module = (
            self.__live.user_stream_decoder.__module__
        )
        self.__setup_core.user_stream_decoder_class_name = (
            self.__live.user_stream_decoder.__name__
        )
        self.__setup_core.order_encoder_module = (
            self.__live.order_encoder.__module__
        )
        self.__setup_core.order_encoder_class_name = (
            self.__live.order_encoder.__name__
        )

        self.__setup_core.backtesting = False

    @error_handler()
    def run_vis(self, auto_open: bool = True) -> None:
        if self.is_backtest_mode:
            self.__vis_logger()

            from imprint.core.constant import (
                BASE_FOOTPRINT_DUMP_PATH,
                EQUITY_HISTORY_DUMP_PATH,
                ORDERS_HISTORY_DUMP_PATH,
            )
            from imprint.visualization import Render

            Render(
                footprint_headers_path=BASE_FOOTPRINT_DUMP_PATH,
                symbol=self.__coin.symbol,
                start_date_str=self.__backtest.backtest_start_date,
                end_date_str=self.__backtest.backtest_end_date,
                equity_history_path=EQUITY_HISTORY_DUMP_PATH,
                orders_history_path=ORDERS_HISTORY_DUMP_PATH,
                start_balance=self.__backtest.account.balance,
                price_mult=self.__coin.price_mult,
                qty_mult=self.__coin.qty_mult,
                scale_mult=self.__backtest.account.scale_mult,
                leverage=self.__backtest.account.leverage,
                timeframe=self.strategy.footprint.timeframe,
                auto_open=auto_open,
            )

    @error_handler()
    def run_core(self) -> None:
        self.__init_data()
        self.__core_logger()

        from imprint.core.main import run

        run(**self.__kwargs)

    def __init_data(self) -> None:
        self.__api_logger()

        from imprint.core.utils import DownloadAggTradesHistory

        if self.is_backtest_mode:
            try:
                DownloadAggTradesHistory(
                    logger=logger,
                    symbol=self.symbol,
                    start_date_str=self.__backtest.backtest_start_date,
                    end_date_str=self.__backtest.backtest_end_date,
                    price_mult=self.__coin.price_mult,
                    qty_mult=self.__coin.qty_mult,
                ).download()
            except DownloadError as e:
                return logger.error(f"Init data failed: {e}")

        else:
            # rest = RestAgent(setup.symbol, setup.run_mode.connector)
            self.__coin.tick_size = "0.01"  # rest.get_tick_size()
            self.__coin.lot_size = "0.001"  # rest.get_lot_size()

    def __api_logger(self) -> None:
        logger.remove()

        from imprint.core.constant import API_LOG_PATH

        logger.add(
            API_LOG_PATH,
            format="{time:YY:MM:DD-HH:mm:ss} | {level} | {message}",
        )

    def __core_logger(self) -> None:
        logger.remove()

        from imprint.core.constant import CORE_LOG_PATH

        logger.add(
            CORE_LOG_PATH,
            format=(
                ("{elapsed} | " if self.is_backtest_mode else "")
                + "{extra[time]} | {extra[level]} | {extra[proc_name]} | {message}"
            ),
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )

    def __vis_logger(self) -> None:
        logger.remove()

        from imprint.core.constant import VISUALIZATION_LOG_PATH

        logger.add(
            VISUALIZATION_LOG_PATH,
            format="{time:YY:MM:DD-HH:mm:ss} | {level} | {message}",
        )
