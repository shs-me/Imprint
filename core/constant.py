# Derivatives Trading (USDS Futures) constants
# Production URL
REST_API_PROD_URL = "https://fapi.binance.com"
WS_API_PROD_URL = "wss://ws-fapi.binance.com/ws-fapi/v1"
WS_STREAMS_PROD_URL = "wss://fstream.binance.com"
# Demo URL
REST_API_DEMO_URL = "https://demo-fapi.binance.com"
# Testnet URL
REST_API_TESTNET_URL = "https://testnet.binancefuture.com"
WS_API_TESTNET_URL = "wss://testnet.binancefuture.com/ws-fapi/v1"
WS_STREAMS_TESTNET_URL = "wss://fstream.binancefuture.com"
# Logging Constant
LOGS_PATH = "logs"
CORE_LOG_PATH = f"{LOGS_PATH}/core.log"
# Debug Constant
DUMP_PATH = "dump"
EXC_DUMP_PATH = f"{DUMP_PATH}/exc_dump.json"
# Core Constant
PLUGIN_PATH = "plugin"
# Data Download Constant
DATA_PATH = "data"
DATA_TYPE_AGGTRADES_PATH = "aggTrades"
BASE_UM_AGGTRADES_DAILY_URL = "https://data.binance.vision/um/aggTrades/daily/"

DIRS_LIST = [DATA_PATH, LOGS_PATH, DUMP_PATH, PLUGIN_PATH]
