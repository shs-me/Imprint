from loguru import logger

from ...core import constant
from ...core.main import run_core
from ...core.pipeline.utils.rest_agent import RestAgent
from ...core.utils.handlers import error_handler
from ...core.utils.tools import download_aggTrade_hist_daily_data, to_date
from .configs import Backtesting, SetupCore

__all__ = ["run"]


@error_handler()
def run(setup: SetupCore) -> None:
    logger.remove()
    logger.add(constant.CORE_LOG_PATH, format="{time} | {level} | {message}")
    if isinstance(setup.run_mode, Backtesting):
        try:
            startDate, endDate = to_date(
                [setup.setup.backtest_start_date, setup.setup.backtest_end_date]
            )
        except ValueError as e:
            return logger.error(f"Run Core Failed | {e}")

        download_aggTrade_hist_daily_data(setup.symbol, startDate, endDate)
    else:
        rest = RestAgent(setup.symbol, setup.run_mode.connector)
        setup.coin.tick_size = rest.get_tick_size()
        setup.coin.lot_size = rest.get_lot_size()

    kwargs = {}
    for obj in setup.args:
        kwargs[obj.__class__.__name__] = obj

    logger.remove()
    logger.add(
        constant.CORE_LOG_PATH,
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

            from ... import visualization as vis

            vis.run(
                footprint_headers_path=constant.BASE_FOOTPRINT_DUMP_PATH,
                symbol=setup.coin.symbol,
                start_date=setup.run_mode.backtest_start_date,
                end_date=setup.run_mode.backtest_end_date,
                equity_history_path=constant.EQUITY_HISTORY_DUMP_PATH,
                orders_history_path=constant.ORDERS_HISTORY_DUMP_PATH,
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
