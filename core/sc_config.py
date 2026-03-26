from . import IDpm


class StatusCodes:
    """StatusCode Config"""

    id_info: dict[int, dict[int, str]] = {
        IDpm.parsing: {
            IDpm.parsing_agent: "ParsingAgent",
            IDpm.parsing_daugther: "GridEngine",
        },
        IDpm.logic: {
            IDpm.logic_agent: "LogicAgent",
            IDpm.logic_daugther: "GridReader",
        },
        IDpm.network: {
            IDpm.network_agent: "WSSAgent",
            IDpm.network_daugther: "RESTAgent",
            IDpm.network_sim_agent: "WSSAgent Backtest",
        },
        IDpm.network_sim: {
            IDpm.network_sim_agent: "SimWSSAgent",
            IDpm.network_sim_daugther: "SimRESTAgent",
        },
    }

    general_sc: dict[int, str] = {
        0: "IDLE",
        1: "RUNNING",
        2: "STOPING",
        3: "SYSEXIT",
        4: "SLEEP",
        5: "WACK_UP",
    }
