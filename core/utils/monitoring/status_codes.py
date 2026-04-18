from enum import IntEnum


class StatusCodes(IntEnum):
    label: dict[str, str] | str

    def __new__(cls, id_mapping: dict[str, str] | str):
        value = len(cls.__members__)
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.label = id_mapping
        return obj

    def get_msg(self, proc_name: str = "run_parsing") -> str:
        label = self.label
        return label.get(proc_name, "") if isinstance(label, dict) else label

    IDLE = "IDLE"
    RUN = "RUNNING"
    STOP = "STOPING"
    SLEEP = "SLEEPING"
    WAKE_UP = "WAKE_UP"
    COMPLETE = "pass"
    ERR_RE = "> this value, error sc"
    ERROR = "Error, for more info check exc_info.log"
    WARN_RE = "> this value, warn sc"
    WARN0 = {
        "PARSING": "ParserAgent: AlarmClock: reading lag > safe lag",
        "LOGIC": "",
        "NETWORK": "WssEngine: SetRawData: size/len RawData > DataSizeInBuffer",
        "NETWORK_SIM": "WssSimEngine: SetRawData: size/len RawData > DataSizeInBuffer",
    }
    WARN1 = {
        "PARSING": "ParserAgent: GetDecodeRawData: aggTrade data < 0",
        "LOGIC": "",
        "NETWORK": "",
        "NETWORK_SIM": "WssSimAgent: data preppered",
    }
    WARN2 = {
        "PARSING": "FootprintWriter: InitSession: amount tick in price > 80% array lines",
        "LOGIC": "",
        "NETWORK": "",
        "NETWORK_SIM": "",
    }
    WARN3 = {
        "PARSING": "FootprintWriter: Update: array cols < idx or idx < 0",
        "LOGIC": "",
        "NETWORK": "",
        "NETWORK_SIM": "",
    }
    WARN4 = {
        "PARSING": "FootprintWriter: Update: array lines < idy or idy < 0",
        "LOGIC": "",
        "NETWORK": "",
        "NETWORK_SIM": "",
    }
