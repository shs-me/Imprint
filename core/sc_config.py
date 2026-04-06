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
        if isinstance(label, dict):
            proc_name = proc_name.removeprefix("run_")
            msg = label.get(proc_name, "")
        else:
            msg = label

        return msg

    IDLE = "IDLE"
    RUN = "RUNNING"
    STOP = "STOPING"
    SLEEP = "SLEEPING"
    WAKE_UP = "WAKE_UP"
    ERR_RE = "> this value, error sc"
    ERROR = "Error, for more info check exc_info.log"
    WARN_RE = "> this value, warn sc"
    WARN0 = {
        "parsing": "ParserAgent: AlarmClock: reading lag > safe lag",
        "logic": "",
        "network": "WssEngine: SetRawData: size/len RawData > DataSizeInBuffer",
        "network_sim": "WssSimEngine: SetRawData: size/len RawData > DataSizeInBuffer",
    }
    WARN1 = {
        "parsing": "ParserAgent: GetDecodeRawData: aggTrade data < 0",
        "logic": "",
        "network": "",
        "network_sim": "",
    }
    WARN2 = {
        "parsing": "FootprintWriter: InitSession: amount tick in price > 80% array lines",
        "logic": "",
        "network": "",
        "network_sim": "",
    }
    WARN3 = {
        "parsing": "FootprintWriter: Update: array cols < idx or idx < 0",
        "logic": "",
        "network": "",
        "network_sim": "",
    }
    WARN4 = {
        "parsing": "FootprintWriter: Update: array lines < idy or idy < 0",
        "logic": "",
        "network": "",
        "network_sim": "",
    }
