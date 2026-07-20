import importlib.util

from . import FootprintReader
from ._core import configurations as con
from ._core.engine.base.base_footprint_reader import BaseFootprintReader
from ._core.engine.mode.real.rest_agent import RestAgent
from ._core.main import run_core
from ._core.settings import Timeframe
from ._core.utils.handlers import error_handler
from ._core.utils.tools import download_aggTrade_hist_daily_data, to_date

__all__ = [
    "run",
    "Timeframe",
]
from loguru import logger

from ._core import constant as c


@error_handler()
def run(
    is_backtesting: bool = True,
    with_execution: bool = False,
    with_visuailization_chart: bool = False,
    with_visuailization_statistic: bool = False,
    algorithm: type[FootprintReader] = BaseFootprintReader,
    timeframe: Timeframe = Timeframe._5M,
    symbol: str = "DASHUSDT",
    sim_balance: float = 5000.0,
    sim_taker_commission: float = 0.005,
    sim_maker_commission: float = 0.002,
    sim_min_order_size: float = 5,
    sim_tick_size: str = "0.01",
    sim_lot_size: str = "0.001",
    backtest_start_date: str = "2026-01-01",
    backtest_end_date: str = "2026-01-01",
    laverage: int = 20,
    max_loss_balance: float = 0.1,
    max_lock_balance: float = 0.05,
    entry_quantity: float = 0.005,
    take_profit_deviation: float = 0.05,
    stop_loss_deviation: float = 0.05,
    save_orders_history: bool = False,
    save_footprint_headers: bool = False,
    save_algorithm_metadata: bool = False,
) -> None:
    logger.remove()
    logger.add(
        c.CORE_LOG_PATH,
        rotation="10 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level} | {message}",
    )

    if is_backtesting:
        try:
            startDate, endDate = to_date([backtest_start_date, backtest_end_date])
        except ValueError as e:
            return logger.error(f"Run Core Failed | {e}")

        download_aggTrade_hist_daily_data(symbol, startDate, endDate)

    else:
        rest = RestAgent(symbol)
        sim_tick_size = rest.get_tick_size()
        sim_lot_size = rest.get_lot_size()

    kwargs = {}
    kwargs["backtesting"] = is_backtesting
    kwargs["execution"] = with_execution
    kwargs["algorithm_module"] = algorithm.__module__
    kwargs["algorithm_package"] = algorithm.__name__

    args = (
        con.cfgBacktesting(
            min_order_size=sim_min_order_size,
            taker_commission=sim_taker_commission,
            maker_commission=sim_maker_commission,
            balance=sim_balance,
            backtest_start_date=backtest_start_date,
            backtest_end_date=backtest_end_date,
        ),
        con.cfgFootprint(
            timeframe=timeframe,
            save_fp_headers=save_footprint_headers,
            save_algorithm_metadata=save_algorithm_metadata,
            algorithm_module=algorithm.__module__,
            algorithm_package=algorithm.__name__,
        ),
        con.cfgAccount(
            leverage=laverage,
            max_loss_balance=max_loss_balance,
            max_lock_balance=max_lock_balance,
            entry_qty=entry_quantity,
            TP_dev=take_profit_deviation,
            SL_dev=stop_loss_deviation,
            save_orders_history=save_orders_history,
        ),
        con.cfgCoin(
            symbol=symbol,
            tick_size=sim_tick_size,
            lot_size=sim_lot_size,
        ),
    )

    for obj in args:
        kwargs[obj.__class__.__name__] = obj

    run_core(**kwargs)

    if with_visuailization_chart or with_visuailization_statistic:
        vis_spec = importlib.util.find_spec("gridcore_visualization")
        if vis_spec is not None:
            vis_module = importlib.import_module("gridcore_visualization")
            vis_module.run(
                symbol=symbol,
                timeframe=timeframe,
                price_prec=args[3].price_prec,
                qty_prec=args[3].qty_prec,
                scale=args[2].scale_prec,
                start_date=backtest_start_date,
                end_date=backtest_end_date,
                footprint_headers_path=c.BASE_FOOTPRINT_DUMP_PATH,
                start_balance=sim_balance,
                orders_history_path=c.ORDERS_HISTORY_DUMP_PATH,
                run_chart_visualization=with_visuailization_chart,
                run_statistic_visualization=with_visuailization_statistic,
            )
        else:
            logger.warning('"gridcore-visualization" package not found')
