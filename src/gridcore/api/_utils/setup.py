import importlib.util

from loguru import logger

from ...core import constant
from ...core.engine.mode.real.rest_agent import RestAgent
from ...core.main import run_core
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

            vis_spec = importlib.util.find_spec("gridcore_visualization")
            if vis_spec is not None:
                vis_module = importlib.import_module("gridcore_visualization")
                vis_module.run(
                    symbol=setup.coin.symbol,
                    timeframe=setup.strategy.footprint.timeframe,
                    price_prec=setup.coin.price_prec,
                    qty_prec=setup.coin.qty_prec,
                    scale=setup.run_mode.account.scale_prec,
                    start_date=setup.run_mode.backtest_start_date,
                    end_date=setup.run_mode.backtest_end_date,
                    footprint_headers_path=constant.BASE_FOOTPRINT_DUMP_PATH,
                    start_balance=setup.run_mode.account.balance,
                    orders_history_path=constant.ORDERS_HISTORY_DUMP_PATH,
                    equity_history_path=constant.EQUITY_HISTORY_DUMP_PATH,
                )
            else:
                logger.warning('"gridcore-visualization" package not found')
        else:
            run_core(**kwargs)
    else:
        run_core(**kwargs)
