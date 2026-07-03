from .settings import (
    ActiveOrders,
    BarHeaders,
    CachedStatesData,
    DataForMatching,
    OrderFlag,
    StateFlags,
    TradeParam,
)

# - - URL'S - -
# Derivatives Trading (USDS Futures)
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
# Other
BASE_UM_AGGTRADES_DAILY_URL = (
    "https://data.binance.vision/data/futures/um/daily/aggTrades/"
)

# - - PATH'S - -
# Logging
LOGS_PATH = "logs"
CORE_LOG_PATH = f"{LOGS_PATH}/core.log"
# Core
ALGORITHM_PATH = "algorithms"
# Data Download
DATA_PATH = "data"
DATA_TYPE_AGGTRADES_PATH = "aggTrades"
# Dump
DUMP_PATH = "dump"
EXC_DUMP_PATH = f"{DUMP_PATH}/exc_dump.json"
ORDERS_HISTORY_DUMP_PATH = f"{DUMP_PATH}/order_history.npy"
BASE_FOOTPRINT_DUMP_PATH = f"{DUMP_PATH}/FootprintHeaders"
ALGORITHM_METADATA_DUMP_PATH = f"{DUMP_PATH}/algorithm_metadata.npy"
# Other
DIRS_LIST = [DATA_PATH, LOGS_PATH, DUMP_PATH, ALGORITHM_PATH]

# - - CORE - -
# BarHeader
BH_Open: int = int(BarHeaders.Open)
BH_High: int = int(BarHeaders.High)
BH_Low: int = int(BarHeaders.Low)
BH_Close: int = int(BarHeaders.Close)
BH_Volume: int = int(BarHeaders.Volume)
BH_Delta: int = int(BarHeaders.Delta)
BH_CVD: int = int(BarHeaders.CVD)
BH_VWAP: int = int(BarHeaders.VWAP)
BH_VWAP_BB_UPPER: int = int(BarHeaders.VWAP_BB_UPPER)
BH_VWAP_BB_LOWER: int = int(BarHeaders.VWAP_BB_LOWER)
BH_Time: int = int(BarHeaders.OpenTime)
BH_LastTradeTime: int = int(BarHeaders.LastTradeTime)
BH_CountTrade: int = int(BarHeaders.CountTrade)
BH_ATR: int = int(BarHeaders.ATR)
BH_POC: int = int(BarHeaders.POC)
BH_VAH: int = int(BarHeaders.VAH)
BH_VAL: int = int(BarHeaders.VAL)
BH_ConstantCount: int = int(BarHeaders._ConstantCount)

# StateFlag
SF_BID_DELTA_DOMINATION_FP: int = int(StateFlags.BID_DELTA_DOMINATION_FP)
SF_ASK_DELTA_DOMINATION_FP: int = int(StateFlags.ASK_DELTA_DOMINATION_FP)
SF_VWAP: int = int(StateFlags.VWAP)
SF_UPPER_BB: int = int(StateFlags.UPPER_BB)
SF_LOWER_BB: int = int(StateFlags.LOWER_BB)
SF_POC_FP: int = int(StateFlags.POC_FP)
SF_VAL_FP: int = int(StateFlags.VAL_FP)
SF_VAH_FP: int = int(StateFlags.VAH_FP)
SF_OPEN: int = int(StateFlags.OPEN)
SF_CLOSE: int = int(StateFlags.CLOSE)
SF_HIGH: int = int(StateFlags.HIGH)
SF_LOW: int = int(StateFlags.LOW)
SF_POC_BAR: int = int(StateFlags.POC_BAR)
SF_VAL_BAR: int = int(StateFlags.VAL_BAR)
SF_VAH_BAR: int = int(StateFlags.VAH_BAR)
SF_UNFINISHED_AUCTION: int = int(StateFlags.UNFINISHED_AUCTION)
SF_FINISHED_AUCTION: int = int(StateFlags.FINISHED_AUCTION)
SF_ABSORPTION: int = int(StateFlags.ABSORPTION)
SF_EXHAUSTION: int = int(StateFlags.EXHAUSTION)
SF_DELTA_DOMINATION: int = int(StateFlags.DELTA_DOMINATION)
SF_ZERO_PRINT: int = int(StateFlags.ZERO_PRINT)
SF_IMBALANCE: int = int(StateFlags.IMBALANCE)
SF_BIG_TRADE: int = int(StateFlags.BIG_TRADE)

# CachedStates
CSD_VWAP: int = int(CachedStatesData.VWAP)
CSD_UPPER_BB: int = int(CachedStatesData.UPPER_BB)
CSD_LOWER_BB: int = int(CachedStatesData.LOWER_BB)
CSD_POC_FP: int = int(CachedStatesData.POC_FP)
CSD_VAH_FP: int = int(CachedStatesData.VAH_FP)
CSD_VAL_FP: int = int(CachedStatesData.VAL_FP)
CSD_ConstantCount: int = int(CachedStatesData._ConstantCount)

# DataForMatching
DFM_nPrice: int = int(DataForMatching.nPrice)
DFM_startTimestamp: int = int(DataForMatching.startTimestamp)
DFM_endTimestamp: int = int(DataForMatching.endTimestamp)
DFM_ConstantCount: int = int(DataForMatching._ConstantCount)

# Active Orders
AO_nPrice: int = int(ActiveOrders.nPrice)
AO_nQty: int = int(ActiveOrders.nQty)
AO_timestamp: int = int(ActiveOrders.timestamp)
AO_orderParam: int = int(ActiveOrders.orderParam)
AO_orderID: int = int(ActiveOrders.orderID)
AO_ConstantCount: int = int(ActiveOrders._ConstantCount)

# Trade Param
TP_nPrice: int = int(TradeParam.nPrice)
TP_nQty: int = int(TradeParam.nQty)
TP_timestamp: int = int(TradeParam.timestamp)
TP_orderParam: int = int(TradeParam.orderParam)
TP_orderID: int = int(TradeParam.orderID)
TP_commission: int = int(TradeParam.nCommission)
TP_ConstantCount: int = int(TradeParam._ConstantCount)

# OrderFlag
OF_LONG: int = int(OrderFlag.LONG)
OF_SHORT: int = int(OrderFlag.SHORT)
OF_BUY: int = int(OrderFlag.BUY)
OF_SELL: int = int(OrderFlag.SELL)
OF_LIMIT: int = int(OrderFlag.LIMIT)
OF_MARKET: int = int(OrderFlag.MARKET)
OF_MARKET_TRIGER: int = int(OrderFlag.MARKET_TRIGER)
OF_LIMIT_TRIGER: int = int(OrderFlag.LIMIT_TRIGER)
OF_NEW: int = int(OrderFlag.NEW)
OF_FILLED: int = int(OrderFlag.FILLED)
OF_CANCELED: int = int(OrderFlag.CANCELED)

# Tool's setup
ATR_PERIOD: int = 14
