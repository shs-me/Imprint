from core.configurations import ConfigurationBacktesting, ConfigurationFootprint
from core.main import run_core
from core.settings import BacktestingMode as bm
from core.settings import ChartInterval
from core.utils.tools import get_configs_kwargs

symbol = "DASHUSDT"
cfgFootprint = ConfigurationFootprint(chart_interval=ChartInterval._5M)
cfgBacktesting = ConfigurationBacktesting()
kwargs = get_configs_kwargs(cfgFootprint, cfgBacktesting)

if __name__ == "__main__":
    run_core(backtesting=True, mode=bm.ZERO_SLEEP, symbol=symbol, **kwargs)
