from enum import Enum

from . import FootprintReader
from ._core import configurations as con
from ._core.engine.base.base_footprint_reader import BaseFootprintReader
from ._core.main import run_core
from ._core.settings import Timeframe
from ._core.utils.handlers import error_handler

__all__ = [
    "run_live",
    "run_backtesting",
    "Timeframe",
]


class RunMode(Enum):
    Backtesting = True, True
    Real = False, True


def run_live(
    algorithm: type[FootprintReader] = BaseFootprintReader,
    symbol: str = "DASHUSDT",
    timeframe: Timeframe = Timeframe._5M,
    laverage: int = 20,
    max_loss_balance: float = 0.1,
    max_lock_balance: float = 0.05,
    entry_quantity: float = 0.005,
    take_profit_deviation: float = 0.05,
    stop_loss_deviation: float = 0.05,
) -> None:
    _run(
        algorithm=algorithm,
        run_mode=RunMode.Real,
        symbol=symbol,
        timeframe=timeframe,
        laverage=laverage,
        max_loss_balance=max_loss_balance,
        max_lock_balance=max_lock_balance,
        entry_quantity=entry_quantity,
        take_profit_deviation=take_profit_deviation,
        stop_loss_deviation=stop_loss_deviation,
    )


def run_backtesting(
    algorithm: type[FootprintReader] = BaseFootprintReader,
    backtest_start_date: str = "2026-01-01",
    backtest_end_date: str = "2026-01-01",
    symbol: str = "DASHUSDT",
    sim_tick_size: str = "0.01",
    sim_lot_size: str = "0.001",
    sim_taker_commission: float = 0.005,
    sim_maker_commission: float = 0.002,
    sim_min_order_size: float = 5.0,
    sim_balance: float = 5000.0,
    timeframe: Timeframe = Timeframe._5M,
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
    _run(
        algorithm=algorithm,
        run_mode=RunMode.Backtesting,
        backtest_start_date=backtest_start_date,
        backtest_end_date=backtest_end_date,
        symbol=symbol,
        sim_tick_size=sim_tick_size,
        sim_lot_size=sim_lot_size,
        sim_balance=sim_balance,
        sim_taker_commission=sim_taker_commission,
        sim_maker_commission=sim_maker_commission,
        sim_min_order_size=sim_min_order_size,
        timeframe=timeframe,
        laverage=laverage,
        max_loss_balance=max_loss_balance,
        max_lock_balance=max_lock_balance,
        entry_quantity=entry_quantity,
        take_profit_deviation=take_profit_deviation,
        stop_loss_deviation=stop_loss_deviation,
        save_orders_history=save_orders_history,
        save_footprint_headers=save_footprint_headers,
        save_algorithm_metadata=save_algorithm_metadata,
    )


@error_handler()
def _run(
    algorithm: type[FootprintReader] = BaseFootprintReader,
    run_mode: RunMode = RunMode.Backtesting,
    timeframe: Timeframe = Timeframe._5M,
    symbol: str = "DASHUSDT",
    laverage: int = 20,
    max_loss_balance: float = 0.1,
    max_lock_balance: float = 0.05,
    entry_quantity: float = 0.005,
    take_profit_deviation: float = 0.05,
    stop_loss_deviation: float = 0.05,
    sim_balance: float = 5000.0,
    sim_taker_commission: float = 0.005,
    sim_maker_commission: float = 0.002,
    sim_min_order_size: float = 5,
    sim_tick_size: str = "0.01",
    sim_lot_size: str = "0.001",
    backtest_start_date: str = "2026-01-01",
    backtest_end_date: str = "2026-01-01",
    save_orders_history: bool = False,
    save_footprint_headers: bool = False,
    save_algorithm_metadata: bool = False,
) -> None:
    execution, backtesting = run_mode.value

    kwargs = {}
    kwargs["backtesting"] = backtesting
    kwargs["execution"] = execution
    kwargs["symbol"] = symbol
    kwargs["algorithm_module"] = algorithm.__module__
    kwargs["algorithm_package"] = algorithm.__name__

    args = (
        con.ConfigurationBacktesting(
            tick_size=sim_tick_size,
            lot_size=sim_lot_size,
            minOrderSizeUSDT=sim_min_order_size,
            taker_commission=sim_taker_commission,
            maker_commission=sim_maker_commission,
            balanceUSDT=sim_balance,
            execution_sim=execution,
            startDateForPrepper=backtest_start_date,
            endDateForPrepper=backtest_end_date,
        ),
        con.ConfigurationFootprint(
            timeframe=timeframe,
            saveFootprintHeaders=save_footprint_headers,
            saveAlgorithmMetadata=save_algorithm_metadata,
        ),
        con.ConfigurationStrategy(
            leverage=laverage,
            maxLossBalance=max_loss_balance,
            maxLockBalance=max_lock_balance,
            entry_qty=entry_quantity,
            TPdev=take_profit_deviation,
            SLdev=stop_loss_deviation,
            saveOrdersHistory=save_orders_history,
        ),
    )

    for obj in args:
        name = str(obj.__class__).split(".")[-1].removesuffix("'>")
        kwargs[name] = obj

    run_core(**kwargs)
