from . import IDpm, ProcsDictTyping, run_monitoring
from .engine import run_logic, run_parsing, run_wss, run_wss_sim


class ProcsCfg:
    """StatusCode & Process Config"""

    procs: dict[int, ProcsDictTyping] = {
        IDpm.parsing: {"name": "PARSING", "func": run_parsing, "proc": None},
        IDpm.logic: {"name": "LOGIC", "func": run_logic, "proc": None},
        IDpm.network: {"name": "NETWORK", "func": run_wss, "proc": None},
        IDpm.network_sim: {
            "name": "NETWORK_SIM",
            "func": run_wss_sim,
            "proc": None,
        },
        IDpm.monitoring: {
            "name": "MONITORING",
            "func": run_monitoring,
            "proc": None,
        },
    }
