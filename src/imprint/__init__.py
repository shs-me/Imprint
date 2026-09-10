from dataclasses import dataclass, field
from typing import final

from loguru import logger

from imprint import configs
from imprint._core import constant
from imprint._core.configs import Coin as _Coin
from imprint._core.configs import Configuration as _Cfg
from imprint._core.configs import Percent as pct
from imprint._core.configs import Setup as _Setup
from imprint._core.pipeline.executing import BaseExecution
from imprint._core.settings import Timeframe as tf
from imprint._core.utils.agg_trades_history_downloader import DownloadError
from imprint._core.utils.base_adapters import ApiNotFoundError
from imprint._core.utils.exc_dumper import error_handler

__all__ = [
    "Imprint",
    "configs",
    "constant",
    "pct",
    "tf",
]


@final
@dataclass(slots=True)
class Imprint:
    run_mode: (
        configs.Backtest
        | configs.Live
        | tuple[
            type[configs.Backtest | configs.Live],
            configs.Backtest,
            configs.Live,
        ]
    )
    symbol: str
    strategy: configs.Strategy
    execution: type[BaseExecution]

    with_execution: bool = field(default=False)

    __coin: _Coin = field(init=False)
    __account: configs.Account = field(init=False)
    __setup_core: _Setup = field(init=False)
    __kwargs: dict[str, _Cfg] = field(default_factory=dict, init=False)
    __backtest: configs.Backtest = field(init=False)
    __live: configs.Live = field(init=False)
    __init_complete: bool = field(init=False)
    __rest: configs.ExchangeREST = field(init=False)

    def __post_init__(self) -> None:
        self.__init_logger()

        logger.info("Init, started.")

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
        else:
            self.__live_setup()
            args.append(self.__live.connector)

        if self.with_execution:
            self.__setup_core.execution = True
            self.__setup_core.execution_module = self.execution.__module__
            self.__setup_core.execution_class_name = self.execution.__name__
        else:
            self.__setup_core.execution = False

        self.__init_complete = self.__init_data()

        logger.info(
            f"Init, {'completed' if self.__init_complete else 'failed'}.\n"
        )
        args.append(self.__coin)
        args.append(self.__account)
        args.append(self.__setup_core)

        for obj in args:
            self.__kwargs[obj.__class__.__name__] = obj

    @property
    def is_backtest_mode(self) -> bool:
        if (not hasattr(self, f"_{Imprint.__name__}__backtest")) and (
            not hasattr(self, f"_{Imprint.__name__}__live")
        ):
            if isinstance(self.run_mode, tuple):
                if self.run_mode[0] is configs.Backtest:
                    self.__backtest = self.run_mode[1]
                else:
                    self.__live = self.run_mode[2]
            else:
                if isinstance(self.run_mode, configs.Backtest):
                    self.__backtest = self.run_mode
                else:
                    self.__live = self.run_mode

        return hasattr(self, f"_{Imprint.__name__}__backtest")

    def __init_logger(self) -> None:
        import imprint
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
            filter=lambda r: r["name"].endswith(imprint.__name__),  # pyright: ignore[reportOptionalMemberAccess]
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )
        logger.add(
            CORE_LOG_PATH,
            format=(
                ("{elapsed} | " if self.is_backtest_mode else "")
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

    def __backtest_setup(self) -> None:
        self.__setup_core.backtest_start_date = (
            self.__backtest.backtest_start_date
        )
        self.__setup_core.backtest_end_date = self.__backtest.backtest_end_date
        self.__setup_core.backtesting = True

        self.__account = self.__backtest.account

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
        self.__setup_core.exchange_rest_module = (
            self.__live.exchange_rest.__module__
        )
        self.__setup_core.exchange_rest_class_name = (
            self.__live.exchange_rest.__name__
        )
        self.__setup_core.backtesting = False

        self.__account = configs.Account()

    def __init_data(self) -> bool:
        if self.is_backtest_mode:
            from imprint._core.utils import DownloadAggTradesHistory

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
                logger.error(f"Init data, failed: {e}")
                return False
        else:
            self.__rest = self.__live.exchange_rest(
                logger=logger, symbol=self.symbol
            )
            self.__rest.base_url = self.__live.connector.base_rest_url
            self.__coin.tick_size = self.__rest.tick_size
            self.__coin.lot_size = self.__rest.lot_size
            self.__account.min_order_size = self.__rest.min_order_size
            self.__account.leverage = self.__rest.leverage
            try:
                self.__account.balance = self.__rest.get_balance()
                if not self.__account.balance:
                    logger.error(
                        f"Init data, failed. Balance({self.__account.leverage}) is not valid"
                    )
                    return False

            except ApiNotFoundError:
                logger.error("Api key or api secret doest exists in env")
                return False

            if not self.__coin.tick_size:
                logger.error(
                    f"Init data, failed. Tick size({self.__coin.tick_size}) is not valid"
                )
                return False
            if not self.__coin.lot_size:
                logger.error(
                    f"Init data, failed. Lot size({self.__coin.lot_size}) is not valid"
                )
                return False
            if not self.__account.min_order_size:
                logger.error(
                    f"Init data, failed. Min order size({self.__account.min_order_size}) is not valid"
                )
                return False
            if not self.__account.leverage:
                logger.error(
                    f"Init data, failed. Leverage({self.__account.leverage}) is not valid"
                )
                return False

        return True

    @error_handler()
    def run_vis(self, auto_open: bool = True) -> None:
        if self.__init_complete and self.is_backtest_mode:
            from imprint._core.constant import (
                EQUITY_HISTORY_DATA_PATH,
                FOOTPRINT_HEADERS_DATA_PATH,
                ORDERS_HISTORY_DATA_PATH,
            )
            from imprint._vis.main import Render

            logger.info("Visualization, started.")
            Render(
                footprint_headers_path=FOOTPRINT_HEADERS_DATA_PATH,
                symbol=self.__coin.symbol,
                start_date_str=self.__backtest.backtest_start_date,
                end_date_str=self.__backtest.backtest_end_date,
                equity_history_path=EQUITY_HISTORY_DATA_PATH,
                orders_history_path=ORDERS_HISTORY_DATA_PATH,
                start_balance=self.__backtest.account.balance,
                price_mult=self.__coin.price_mult,
                qty_mult=self.__coin.qty_mult,
                scale_mult=self.__backtest.account.scale_mult,
                leverage=self.__backtest.account.leverage,
                timeframe=self.strategy.footprint.timeframe,
                auto_open=auto_open,
            )
            logger.info("Visualization, closed.\n")

    @error_handler()
    def run_core(self) -> None:
        if self.__init_complete:
            from imprint._core.main import run

            logger.info(
                f"Core in {'configs.Backtest' if self.is_backtest_mode else 'configs.Live'} mode, started."
            )
            run(**self.__kwargs)
            logger.info("Core, closed.\n")
