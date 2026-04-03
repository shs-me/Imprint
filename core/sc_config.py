from enum import IntEnum

from . import IDpm


class StatusCodes(IntEnum):
    label: dict[IDpm, str] | str

    def __new__(cls, id_mapping: dict[IDpm, str] | str):
        last_value = len(cls.__members__)
        value = last_value + 1 if last_value != 0 else 0
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj.label = id_mapping
        return obj

    def get_msg(self, id_m: IDpm = IDpm.logic) -> str:
        label = self.label
        msg = label.get(id_m, "") if isinstance(label, dict) else label
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
        IDpm.parsing_agent: "AlarmClock: reading lag > safe lag",
        IDpm.parsing_daugther: "InitSession: amount ticks in price > 80% of lines",
        IDpm.logic_agent: "",
        IDpm.logic_daugther: "",
        IDpm.network_agent: "SetRawData: size/len RawData > DataSizeInBuffer",
        IDpm.network_daugther: "",
        IDpm.network_sim_agent: "SetRawData: size/len RawData > DataSizeInBuffer",
        IDpm.network_sim_daugther: "",
    }
    WARN1 = {
        IDpm.parsing_agent: "DecodeRawData: data < 0",
        IDpm.parsing_daugther: "Update: IDX > ArrayCols or IDX < 0",
        IDpm.logic_agent: "",
        IDpm.logic_daugther: "",
        IDpm.network_agent: "",
        IDpm.network_daugther: "",
        IDpm.network_sim_agent: "",
        IDpm.network_sim_daugther: "",
    }
    WARN2 = {
        IDpm.parsing_agent: "",
        IDpm.parsing_daugther: "InitSession: 102 : IDY > ArrayLines or IDY < 0",
        IDpm.logic_agent: "",
        IDpm.logic_daugther: "",
        IDpm.network_agent: "",
        IDpm.network_daugther: "",
        IDpm.network_sim_agent: "",
        IDpm.network_sim_daugther: "",
    }
    WARN3 = {
        IDpm.parsing_agent: "",
        IDpm.parsing_daugther: "",
        IDpm.logic_agent: "",
        IDpm.logic_daugther: "",
        IDpm.network_agent: "",
        IDpm.network_daugther: "",
        IDpm.network_sim_agent: "",
        IDpm.network_sim_daugther: "",
    }
    WARN4 = {
        IDpm.parsing_agent: "",
        IDpm.parsing_daugther: "",
        IDpm.logic_agent: "",
        IDpm.logic_daugther: "",
        IDpm.network_agent: "",
        IDpm.network_daugther: "",
        IDpm.network_sim_agent: "",
        IDpm.network_sim_daugther: "",
    }
