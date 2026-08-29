from loguru import logger

from ...core.configs import Configuration
from ...core.constant import (
    BASE_FOOTPRINT_DUMP_PATH,
    CORE_LOG_PATH,
    EQUITY_HISTORY_DUMP_PATH,
    ORDERS_HISTORY_DUMP_PATH,
)
from ...core.main import run_core
from ...core.pipeline.utils.rest_agent import RestAgent
from ...core.utils.handlers import error_handler
from ...core.utils.tools import download_agg_trades_history, to_date
from .configs import Backtesting, SetupCore

__all__ = ["run"]


@error_handler()
def run(setup: SetupCore) -> None:
    logger.remove()
    logger.add(CORE_LOG_PATH, format="{time} | {level} | {message}")
    if isinstance(setup.run_mode, Backtesting):
        try:
            startDate, endDate = to_date(
                [setup.setup.backtest_start_date, setup.setup.backtest_end_date]
            )
        except ValueError as e:
            return logger.error(f"Run Core Failed | {e}")

        download_agg_trades_history(
            setup.symbol, startDate, endDate, setup.coin.price_mult, setup.coin.qty_mult
        )
    else:
        # rest = RestAgent(setup.symbol, setup.run_mode.connector)
        setup.coin.tick_size = "0.01"  # rest.get_tick_size()
        setup.coin.lot_size = "0.001"  # rest.get_lot_size()

    kwargs: dict[str, Configuration] = {}
    for obj in setup.args:
        kwargs[obj.__class__.__name__] = obj

    logger.remove()
    logger.add(
        CORE_LOG_PATH,
        format=(
            ("{elapsed} | " if setup.setup.backtesting else "")
            + "{extra[time]} | {extra[level]} | {extra[proc_name]} | {message}"
        ),
        rotation="10 MB",
        colorize=True,
        enqueue=True,
    )
    if isinstance(setup.run_mode, Backtesting):
        if setup.run_mode.with_visualization:
            if not setup.run_mode.with_visualization.only_visualization:
                run_core(**kwargs)

            from ...visualization import run as run_vis

            run_vis(
                footprint_headers_path=BASE_FOOTPRINT_DUMP_PATH,
                symbol=setup.coin.symbol,
                start_date=setup.run_mode.backtest_start_date,
                end_date=setup.run_mode.backtest_end_date,
                equity_history_path=EQUITY_HISTORY_DUMP_PATH,
                orders_history_path=ORDERS_HISTORY_DUMP_PATH,
                start_balance=setup.run_mode.account.balance,
                price_mult=setup.coin.price_mult,
                qty_mult=setup.coin.qty_mult,
                scale_mult=setup.run_mode.account.scale_mult,
                leverage=setup.run_mode.account.leverage,
                timeframe=setup.strategy.footprint.timeframe,
            )

        else:
            run_core(**kwargs)
    else:
        run_core(**kwargs)
