from . import IDpm, ProcsDictTyping  # ,  run_monitoring
from .engine import run_logic, run_network, run_network_sim, run_parsing


class ProcsCfg:
    """
    StatusCode & Process Config
    # IDpm.monitoring: {
        "name": "MONITORING",
        "func": run_monitoring,
        "proc": None,
    },
    """

    procs: dict[int, ProcsDictTyping] = {
        IDpm.parsing: {"name": "PARSING", "func": run_parsing, "proc": None},
        IDpm.logic: {"name": "LOGIC", "func": run_logic, "proc": None},
        IDpm.network: {"name": "NETWORK", "func": run_network, "proc": None},
        IDpm.network_sim: {
            "name": "NETWORK_SIM",
            "func": run_network_sim,
            "proc": None,
        },
    }
