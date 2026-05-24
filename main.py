from core.configurations import (
    ConfigurationBacktesting,
    ConfigurationFootprint,
    ConfigurationStrategy,
)
from core.main import run_core
from core.settings import BacktestingMode as bm
from core.settings import ChartInterval
from core.utils.tools import download_aggTrade_hist_daily_data as download
from core.utils.tools import get_configs_kwargs, to_date


def download_data(
    symbol: str,
    startYear: int,
    startMonth: int,
    startDay: int,
    endYear: int,
    endMonth: int,
    endDay: int,
) -> None:
    startDate = to_date(startYear, startMonth, startDay)
    endDate = to_date(endYear, endMonth, endDay)
    download(symbol, startDate, endDate)


if __name__ == "__main__":
    symbol = "DASHUSDT"
    cfgFootprint = ConfigurationFootprint(
        chart_interval=ChartInterval._5M,
        saveFootprintHeaders=False,
        saveAlgorithmMetadata=False,
    )
    cfgBacktesting = ConfigurationBacktesting(
        balanceUSDT=1000,
        execution_sim=True,
        startDateForPrepper="2025-01-01",
        endDateForPrepper="2025-08-28",
    )
    cfgStrategy = ConfigurationStrategy(
        leverage=20,
        maxLossBalance=0.2,
        maxLockBalance=0.2,
        entry_qty=0.005,
        TPdev=0.05,
        SLdev=0.05,
        saveOrdersHistory=True,
    )
    kwargs = get_configs_kwargs(cfgFootprint, cfgBacktesting, cfgStrategy)

    run_core(
        backtesting=True, execution=True, mode=bm.ZERO_SLEEP, symbol=symbol, **kwargs
    )
