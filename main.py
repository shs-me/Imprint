from core import run_core
from core.configurations import ConfigurationBacktesting, ConfigurationFootprint
from core.utils.tools import get_configs_kwargs

cfgFootprint = ConfigurationFootprint()
cfgBacktesting = ConfigurationBacktesting()
kwargs = get_configs_kwargs(cfgFootprint, cfgBacktesting)

if __name__ == "__main__":
    run_core(backtesting=True, **kwargs)
