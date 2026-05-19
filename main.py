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
        chart_interval=ChartInterval._5M, save_headers_as_csv=False
    )
    cfgBacktesting = ConfigurationBacktesting(
        balanceUSDT=1000,
        startDateForPrepper="2025-10-01",
        endDateForPrepper="2025-10-30",
    )
    cfgStrategy = ConfigurationStrategy(
        leverage=50,
        maxLossBalance=0.2,
        maxLockBalance=0.1,
        entry_qty=0.005,
        TPdev=0.02,
        SLdev=0.02,
    )
    kwargs = get_configs_kwargs(cfgFootprint, cfgBacktesting, cfgStrategy)

    run_core(backtesting=True, mode=bm.ZERO_SLEEP, symbol=symbol, **kwargs)
