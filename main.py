from core import run_core
from core.configurations import ConfigurationBacktesting, ConfigurationFootprint
from core.settings import BacktestingMode as bm
from core.utils.tools import get_configs_kwargs

cfgFootprint = ConfigurationFootprint()
cfgBacktesting = ConfigurationBacktesting(backtesting=True, mode=bm.ZERO_SLEEP)
kwargs = get_configs_kwargs(cfgFootprint, cfgBacktesting)

if __name__ == "__main__":
    run_core(backtesting=True, **kwargs)
