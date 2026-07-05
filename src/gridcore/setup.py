from enum import Enum

from ._core.configurations import (
    ConfigurationBacktesting,
    ConfigurationFootprint,
    ConfigurationStrategy,
)
from ._core.main import run_core
from ._core.settings import Timeframe
from ._core.utils.tools import download_data

__all__ = [
    "run",
    "download_data",
    "Timeframe",
    "RunMode",
]


class RunMode(Enum):
    Backtesting = True, True
    Real = False, True


def run(
    run_mode: RunMode,
    timeframe: Timeframe,
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
    args = (
        ConfigurationBacktesting(
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
        ConfigurationFootprint(
            timeframe=timeframe,
            saveFootprintHeaders=save_footprint_headers,
            saveAlgorithmMetadata=save_algorithm_metadata,
        ),
        ConfigurationStrategy(
            leverage=laverage,
            maxLossBalance=max_loss_balance,
            maxLockBalance=max_lock_balance,
            entry_qty=entry_quantity,
            TPdev=take_profit_deviation,
            SLdev=stop_loss_deviation,
            saveOrdersHistory=save_orders_history,
        ),
    )

    kwargs = {}
    kwargs["backtesting"] = backtesting
    kwargs["execution"] = execution
    kwargs["symbol"] = symbol

    for obj in args:
        name = str(obj.__class__).split(".")[-1].removesuffix("'>")
        kwargs[name] = obj

    run_core(**kwargs)
