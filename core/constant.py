# Derivatives Trading (USDS Futures) constants
# Production
REST_API_PROD_URL = "https://fapi.binance.com"
WS_API_PROD_URL = "wss://ws-fapi.binance.com/ws-fapi/v1"
WS_STREAMS_PROD_URL = "wss://fstream.binance.com"
# Demo
REST_API_DEMO_URL = "https://demo-fapi.binance.com"
# Testnet
REST_API_TESTNET_URL = "https://testnet.binancefuture.com"
WS_API_TESTNET_URL = "wss://testnet.binancefuture.com/ws-fapi/v1"
WS_STREAMS_TESTNET_URL = "wss://fstream.binancefuture.com"


class CorePath:
    dirs = ["plugins", "dump", "data", "logs"]
    core_log = "logs/_core_.log"
    profiling_log = "logs/profiling.log"
    data_csv = "data/aggtrades.csv"
    algoritm_path = "plugins/algorithm.py"
    exc_dump = "dump/exc_dump.json"
    profiling_bin = "dump/profiling.bin"
    profiling_csv = "dump/profiling.csv"
    pheaders_csv = "dump/pheaders.csv"
