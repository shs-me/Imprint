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
from imprint.core.configs import (
    Coin as _Coin,
)
from imprint.core.configs import (
    Configuration as _Cfg,
)
from imprint.core.configs import (
    Setup as _Setup,
)
from imprint.core.footprint import FootprintEngine
from imprint.core.pipeline.executing import BaseExecution
from imprint.core.pipeline.utils.base_adapters import (
    AggTradesDecoder,
    OrderEncoder,
    UserStreamDecoder,
)
from imprint.core.settings import Timeframe
from imprint.core.utils.handlers import error_handler

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
    run_mode: type[Backtest | Live]
    backtest: Backtest
    live: Live
    symbol: str
    strategy: Strategy
    execution: type[BaseExecution]

    with_execution: bool = field(default=False)

    coin: _Coin = field(init=False)
    setup_core: _Setup = field(init=False)

    kwargs: dict[str, _Cfg] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        args: list[_Cfg] = [
            self.strategy.risk_management,
            self.strategy.footprint,
        ]
        self.coin = _Coin(symbol=self.symbol)
        self.setup_core = _Setup(
            algorithm_module=self.strategy.algorithm.__module__,
            algorithm_class_name=self.strategy.algorithm.__name__,
        )

        if self.run_mode is Backtest:
            self.setup_core.backtest_start_date = (
                self.backtest.backtest_start_date
            )
            self.setup_core.backtest_end_date = self.backtest.backtest_end_date
            self.setup_core.backtesting = True

            self.coin.tick_size = self.backtest.tick_size
            self.coin.lot_size = self.backtest.lot_size

            args.append(self.coin)
            args.append(self.backtest.account)

        else:
            self.setup_core.agg_trades_decoder_module = (
                self.live.agg_trades_decoder.__module__
            )
            self.setup_core.agg_trades_decoder_class_name = (
                self.live.agg_trades_decoder.__name__
            )
            self.setup_core.user_stream_decoder_module = (
                self.live.user_stream_decoder.__module__
            )
            self.setup_core.user_stream_decoder_class_name = (
                self.live.user_stream_decoder.__name__
            )
            self.setup_core.order_encoder_module = (
                self.live.order_encoder.__module__
            )
            self.setup_core.order_encoder_class_name = (
                self.live.order_encoder.__name__
            )

            self.setup_core.backtesting = False

            args.append(self.coin)
            args.append(self.live.connector)

        if self.with_execution:
            self.setup_core.execution = True
            self.setup_core.execution_module = self.execution.__module__
            self.setup_core.execution_class_name = self.execution.__name__
        else:
            self.setup_core.execution = False

        args.append(self.setup_core)

        for obj in args:
            self.kwargs[obj.__class__.__name__] = obj

    @error_handler()
    def run_vis(self, auto_open: bool = True) -> None:
        if self.run_mode is Backtest:
            self.__base_logger()

            from imprint.core.constant import (
                BASE_FOOTPRINT_DUMP_PATH,
                EQUITY_HISTORY_DUMP_PATH,
                ORDERS_HISTORY_DUMP_PATH,
            )
            from imprint.visualization import Render

            Render(
                footprint_headers_path=BASE_FOOTPRINT_DUMP_PATH,
                symbol=self.coin.symbol,
                start_date_str=self.backtest.backtest_start_date,
                end_date_str=self.backtest.backtest_end_date,
                equity_history_path=EQUITY_HISTORY_DUMP_PATH,
                orders_history_path=ORDERS_HISTORY_DUMP_PATH,
                start_balance=self.backtest.account.balance,
                price_mult=self.coin.price_mult,
                qty_mult=self.coin.qty_mult,
                scale_mult=self.backtest.account.scale_mult,
                leverage=self.backtest.account.leverage,
                timeframe=self.strategy.footprint.timeframe,
                auto_open=auto_open,
            )

    @error_handler()
    def run_core(self) -> None:
        self.__init_data()
        self.__core_logger()

        from imprint.core.main import run

        run(**self.kwargs)

    def __init_data(self) -> None:
        self.__base_logger()

        from imprint.core.utils.tools import (
            download_agg_trades_history,
            to_date,
        )

        if self.run_mode is Backtest:
            try:
                startDate, endDate = to_date(
                    [
                        self.setup_core.backtest_start_date,
                        self.setup_core.backtest_end_date,
                    ]
                )
            except ValueError as e:
                return logger.error(f"Run Core Failed | {e}")

            download_agg_trades_history(
                self.symbol,
                startDate,
                endDate,
                self.coin.price_mult,
                self.coin.qty_mult,
            )
        else:
            # rest = RestAgent(setup.symbol, setup.run_mode.connector)
            self.coin.tick_size = "0.01"  # rest.get_tick_size()
            self.coin.lot_size = "0.001"  # rest.get_lot_size()

    def __base_logger(self) -> None:
        logger.remove()

        from imprint.core.constant import CORE_LOG_PATH

        logger.add(CORE_LOG_PATH, format="{time} | {level} | {message}")

    def __core_logger(self) -> None:
        logger.remove()

        from imprint.core.constant import CORE_LOG_PATH

        logger.add(
            CORE_LOG_PATH,
            format=(
                ("{elapsed} | " if self.setup_core.backtesting else "")
                + "{extra[time]} | {extra[level]} | {extra[proc_name]} | {message}"
            ),
            rotation="10 MB",
            colorize=True,
            enqueue=True,
        )
