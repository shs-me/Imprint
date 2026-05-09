from core.configurations import ConfigurationBacktesting, ConfigurationFootprint
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
        chart_interval=ChartInterval._5M, save_headers_as_csv=True
    )
    cfgBacktesting = ConfigurationBacktesting(dayForPrepper=1)
    kwargs = get_configs_kwargs(cfgFootprint, cfgBacktesting)

    run_core(backtesting=True, mode=bm.ZERO_SLEEP, symbol=symbol, **kwargs)
