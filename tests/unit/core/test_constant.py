"""Unit tests for `imprint.core.constant`."""

import imprint._core.constant as c
from imprint._core.settings import (
    BarHeaders,
    CachedStatesData,
    EquityHeaders,
    OrderBook,
    OrderFlag,
    StateFlags,
    TradeParam,
)


class TestBarHeaderAliases:
    def test_all_bar_header_aliases_match_enum_values(self) -> None:
        pairs: dict[str, BarHeaders] = {
            "BH_Open": BarHeaders.Open,
            "BH_High": BarHeaders.High,
            "BH_Low": BarHeaders.Low,
            "BH_Close": BarHeaders.Close,
            "BH_Volume": BarHeaders.Volume,
            "BH_Delta": BarHeaders.Delta,
            "BH_CVD": BarHeaders.CVD,
            "BH_VWAP": BarHeaders.VWAP,
            "BH_VWAP_UPPER_BAND": BarHeaders.VWAP_UPPER_BAND,
            "BH_VWAP_LOWER_BAND": BarHeaders.VWAP_LOWER_BAND,
            "BH_Time": BarHeaders.OpenTime,
            "BH_LastTradeTime": BarHeaders.LastTradeTime,
            "BH_CountTrade": BarHeaders.CountTrade,
            "BH_ATR": BarHeaders.ATR,
            "BH_PARK": BarHeaders.PARK,
            "BH_POC": BarHeaders.POC,
            "BH_VAH": BarHeaders.VAH,
            "BH_VAL": BarHeaders.VAL,
            "BH_POC_FP": BarHeaders.POC_FP,
            "BH_VAH_FP": BarHeaders.VAH_FP,
            "BH_VAL_FP": BarHeaders.VAL_FP,
            "BH_ConstantCount": BarHeaders.ConstantCount,
        }
        for alias_name, enum_member in pairs.items():
            assert getattr(c, alias_name) == int(enum_member)


class TestStateFlagAliases:
    def test_all_state_flag_aliases_match_enum_values(self) -> None:
        pairs: dict[str, StateFlags] = {
            "SF_BID_DELTA_DOMINATION_FP": StateFlags.BID_DELTA_DOMINATION_FP,
            "SF_ASK_DELTA_DOMINATION_FP": StateFlags.ASK_DELTA_DOMINATION_FP,
            "SF_VWAP_FP": StateFlags.VWAP_FP,
            "SF_UPPER_BAND_FP": StateFlags.UPPER_BAND_FP,
            "SF_LOWER_BAND_FP": StateFlags.LOWER_BAND_FP,
            "SF_POC_FP": StateFlags.POC_FP,
            "SF_VAL_FP": StateFlags.VAL_FP,
            "SF_VAH_FP": StateFlags.VAH_FP,
            "SF_OPEN": StateFlags.OPEN,
            "SF_CLOSE": StateFlags.CLOSE,
            "SF_HIGH": StateFlags.HIGH,
            "SF_LOW": StateFlags.LOW,
            "SF_POC_BAR": StateFlags.POC_BAR,
            "SF_VAL_BAR": StateFlags.VAL_BAR,
            "SF_VAH_BAR": StateFlags.VAH_BAR,
            "SF_UNFINISHED_AUCTION": StateFlags.UNFINISHED_AUCTION,
            "SF_FINISHED_AUCTION": StateFlags.FINISHED_AUCTION,
            "SF_ABSORPTION": StateFlags.ABSORPTION,
            "SF_EXHAUSTION": StateFlags.EXHAUSTION,
            "SF_DELTA_DOMINATION": StateFlags.DELTA_DOMINATION,
            "SF_ZERO_PRINT": StateFlags.ZERO_PRINT,
            "SF_IMBALANCE": StateFlags.IMBALANCE,
            "SF_BIG_TRADE": StateFlags.BIG_TRADE,
        }
        for alias_name, enum_member in pairs.items():
            assert getattr(c, alias_name) == int(enum_member)


class TestCachedStatesDataAliases:
    def test_all_aliases_match_enum_values(self) -> None:
        pairs: dict[str, CachedStatesData] = {
            "CSD_VWAP": CachedStatesData.VWAP,
            "CSD_UPPER_BB": CachedStatesData.UPPER_BB,
            "CSD_LOWER_BB": CachedStatesData.LOWER_BB,
            "CSD_POC_FP": CachedStatesData.POC_FP,
            "CSD_VAH_FP": CachedStatesData.VAH_FP,
            "CSD_VAL_FP": CachedStatesData.VAL_FP,
            "CSD_ConstantCount": CachedStatesData.ConstantCount,
        }
        for alias_name, enum_member in pairs.items():
            assert getattr(c, alias_name) == int(enum_member)


class TestOrderBookAliases:
    def test_all_aliases_match_enum_values(self) -> None:
        pairs: dict[str, OrderBook] = {
            "OB_timestamp": OrderBook.timestamp,
            "OB_orderParam": OrderBook.orderParam,
            "OB_clientOrderID": OrderBook.clientOrderID,
            "OB_nPrice": OrderBook.nPrice,
            "OB_nQty": OrderBook.nQty,
            "OB_ConstantCount": OrderBook.ConstantCount,
        }
        for alias_name, enum_member in pairs.items():
            assert getattr(c, alias_name) == int(enum_member)


class TestEquityHeaderAliases:
    def test_all_aliases_match_enum_values(self) -> None:
        pairs: dict[str, EquityHeaders] = {
            "EH_Timestamp": EquityHeaders.Timestamp,
            "EH_Open": EquityHeaders.Open,
            "EH_High": EquityHeaders.High,
            "EH_Low": EquityHeaders.Low,
            "EH_Close": EquityHeaders.Close,
            "EH_ConstantCount": EquityHeaders.ConstantCount,
        }
        for alias_name, enum_member in pairs.items():
            assert getattr(c, alias_name) == int(enum_member)


class TestTradeParamAliases:
    def test_all_aliases_match_enum_values(self) -> None:
        pairs: dict[str, TradeParam] = {
            "TP_nPrice": TradeParam.nPrice,
            "TP_nQty": TradeParam.nQty,
            "TP_timestamp": TradeParam.timestamp,
            "TP_orderParam": TradeParam.orderParam,
            "TP_orderID": TradeParam.orderID,
            "TP_commission": TradeParam.nCommission,
            "TP_nMAE": TradeParam.nMAE,
            "TP_nMFE": TradeParam.nMFE,
            "TP_ConstantCount": TradeParam.ConstantCount,
        }
        for alias_name, enum_member in pairs.items():
            assert getattr(c, alias_name) == int(enum_member)


class TestOrderFlagAliases:
    def test_all_aliases_match_enum_values(self) -> None:
        pairs: dict[str, OrderFlag] = {
            "OF_LONG": OrderFlag.LONG,
            "OF_SHORT": OrderFlag.SHORT,
            "OF_BUY": OrderFlag.BUY,
            "OF_SELL": OrderFlag.SELL,
            "OF_LIMIT": OrderFlag.LIMIT,
            "OF_MARKET": OrderFlag.MARKET,
            "OF_MARKET_TRIGGER": OrderFlag.MARKET_TRIGGER,
            "OF_LIMIT_TRIGGER": OrderFlag.LIMIT_TRIGGER,
            "OF_NEW": OrderFlag.NEW,
            "OF_FILLED": OrderFlag.FILLED,
            "OF_CANCELED": OrderFlag.CANCELED,
            "OF_OCO": OrderFlag.OCO,
        }
        for alias_name, enum_member in pairs.items():
            assert getattr(c, alias_name) == int(enum_member)


class TestPathsAndUrls:
    def test_base_directory_constants(self) -> None:
        assert c.LOGS_PATH == "logs"
        assert c.DATA_PATH == "data"
        assert c.DUMP_PATH == "dump"

    def test_log_path_nested_under_logs_path(self) -> None:
        assert c.CORE_LOG_PATH == f"{c.LOGS_PATH}/core.log"

    def test_dump_paths_nested_under_dump_path(self) -> None:
        assert c.EXC_DUMP_PATH == f"{c.DUMP_PATH}/exc_dump.json"
        assert c.EQUITY_HISTORY_DUMP_PATH == f"{c.DUMP_PATH}/equity_history.npy"
        assert c.ORDERS_HISTORY_DUMP_PATH == f"{c.DUMP_PATH}/order_history.npy"
        assert c.BASE_FOOTPRINT_DUMP_PATH == f"{c.DUMP_PATH}/FootprintHeaders"
        assert (
            c.ALGORITHM_METADATA_DUMP_PATH
            == f"{c.DUMP_PATH}/algorithm_metadata.npy"
        )

    def test_data_type_aggtrades_path(self) -> None:
        assert c.DATA_TYPE_AGGTRADES_PATH == "aggTrades"

    def test_dirs_list_contains_data_logs_and_dump(self) -> None:
        assert c.DIRS_LIST == [c.DATA_PATH, c.LOGS_PATH, c.DUMP_PATH]

    def test_rest_and_ws_urls_are_https_and_wss(self) -> None:
        assert c.REST_API_PROD_URL.startswith("https://")
        assert c.WS_API_PROD_URL.startswith("wss://")
        assert c.WS_STREAMS_PROD_URL.startswith("wss://")
        assert c.REST_API_DEMO_URL.startswith("https://")
        assert c.REST_API_TESTNET_URL.startswith("https://")
        assert c.WS_API_TESTNET_URL.startswith("wss://")
        assert c.WS_STREAMS_TESTNET_URL.startswith("wss://")
        assert c.BASE_UM_AGGTRADES_DAILY_URL.startswith("https://")


class TestToolConstants:
    def test_period_and_scale_constants_are_positive(self) -> None:
        assert c.ATR_PERIOD == 14
        assert c.PARK_PERIOD == 12
        assert c.AVG_VOL_PERIOD == 12
        assert c.VAR_SCALE == 1_000_000_000
