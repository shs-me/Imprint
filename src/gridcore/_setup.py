"""Initialization and setup orchestration module.

Handles configuration object instantiations, historical data downloading for backtesting,
and optional integration with visualization suites.
"""

import importlib.util
from dataclasses import dataclass

from . import FootprintReader
from ._core import configurations as cfg
from ._core.engine.base.base_footprint_reader import BaseFootprintReader
from ._core.engine.mode.real.rest_agent import RestAgent
from ._core.main import run_core
from ._core.settings import Timeframe
from ._core.utils.handlers import error_handler
from ._core.utils.tools import download_aggTrade_hist_daily_data, to_date

__all__ = [
    "run",
    "cfg",
    "RunMode",
    "Analysis",
    "Timeframe",
]

from loguru import logger

from ._core import constant as c


@dataclass
class RunMode:
    """Execution runtime mode configuration container.

    Attributes:
        only_visualization (bool): Flag to run only visualization without core engine execution.
        with_visualization_chart (bool): Enables chart rendering post-execution.
        with_visualization_statistic (bool): Enables performance analytics rendering post-execution.
        backtesting (bool): Enables historical simulation mode.
        execution (bool): Enables order execution pipeline.
        backtest_start_date (str): Backtest window start date (YYYY-MM-DD).
        backtest_end_date (str): Backtest window end date (YYYY-MM-DD).
        setup (cfg.Setup): Internal setup configuration object.
    """

    only_visualization: bool = False
    with_visualization_chart: bool = False
    with_visualization_statistic: bool = False
    backtesting: bool = True
    execution: bool = True
    backtest_start_date: str = "2026-01-01"
    backtest_end_date: str = "2026-01-01"

    def __post_init__(self) -> None:
        """Initializes embedded cfg.Setup dataclass after primary field assignment."""
        self.setup: cfg.Setup = cfg.Setup(
            backtesting=self.backtesting,
            execution=self.execution,
            backtest_start_date=self.backtest_start_date,
            backtest_end_date=self.backtest_end_date,
        )


@dataclass
class Analysis:
    """Footprint analysis algorithm configuration container.

    Attributes:
        algorithm (type[FootprintReader]): User strategy class inheriting from FootprintReader.
        timeframe (Timeframe): Bar aggregation timeframe.
        save_fp_headers (bool): Flag to dump footprint headers to disk.
        save_algorithm_metadata (bool): Flag to dump algorithm execution metadata to disk.
        footprint (cfg.Footprint): Internal footprint configuration object.
    """

    algorithm: type[FootprintReader] = BaseFootprintReader
    timeframe: Timeframe = Timeframe._5M
    save_fp_headers: bool = False
    save_algorithm_metadata: bool = False

    def __post_init__(self) -> None:
        """Instantiates internal Footprint configuration based on provided attributes."""
        self.footprint: cfg.Footprint = cfg.Footprint(
            timeframe=self.timeframe,
            save_fp_headers=self.save_fp_headers,
            save_algorithm_metadata=self.save_algorithm_metadata,
            algorithm_module=self.algorithm.__module__,
            algorithm_class_name=self.algorithm.__name__,
        )


@error_handler()
def run(
    run_mode: RunMode = RunMode(),
    account: cfg.Account = cfg.Account(),
    coin: cfg.Coin = cfg.Coin(),
    strategy: cfg.Strategy = cfg.Strategy(),
    analysis: Analysis = Analysis(),
) -> None:
    """Primary execution launcher for GridCore engine.

    Args:
        run_mode (RunMode): Runtime flags and execution mode configuration.
        account (cfg.Account): Account balances, leverage, and commission settings.
        coin (cfg.Coin): Symbol specification and precision metadata.
        strategy (cfg.Strategy): Risk parameters, entry sizing, and TP/SL deviations.
        analysis (Analysis): Footprint strategy class and timeframe parameters.
    """

    logger.remove()
    logger.add(
        c.CORE_LOG_PATH,
        rotation="10 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    if run_mode.setup.backtesting:
        try:
            startDate, endDate = to_date(
                [run_mode.setup.backtest_start_date, run_mode.setup.backtest_end_date]
            )
        except ValueError as e:
            return logger.error(f"Run Core Failed | {e}")

        download_aggTrade_hist_daily_data(coin.symbol, startDate, endDate)

    else:
        rest = RestAgent(coin.symbol)
        coin.tick_size = rest.get_tick_size()
        coin.lot_size = rest.get_lot_size()

    args = (
        run_mode.setup,
        account,
        coin,
        strategy,
        analysis.footprint,
    )
    kwargs = {}
    for obj in args:
        kwargs[obj.__class__.__name__] = obj

    if not run_mode.only_visualization:
        run_core(**kwargs)

    if run_mode.with_visualization_chart or run_mode.with_visualization_statistic:
        vis_spec = importlib.util.find_spec("gridcore_visualization")
        if vis_spec is not None:
            vis_module = importlib.import_module("gridcore_visualization")
            vis_module.run(
                symbol=coin.symbol,
                timeframe=analysis.timeframe,
                price_prec=coin.price_prec,
                qty_prec=coin.qty_prec,
                scale=account.scale_prec,
                start_date=run_mode.backtest_start_date,
                end_date=run_mode.backtest_end_date,
                footprint_headers_path=c.BASE_FOOTPRINT_DUMP_PATH,
                start_balance=account.balance,
                orders_history_path=c.ORDERS_HISTORY_DUMP_PATH,
                equity_history_path=c.EQUITY_HISTORY_DUMP_PATH,
                run_chart_visualization=run_mode.with_visualization_chart,
                run_statistic_visualization=run_mode.with_visualization_statistic,
            )
        else:
            logger.warning('"gridcore-visualization" package not found')
