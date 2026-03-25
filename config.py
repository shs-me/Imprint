from dataclasses import dataclass
from enum import IntEnum
from multiprocessing import Process
from types import FunctionType
from typing import TypedDict

# from core.src import run_logic, run_monitoring, run_parsing


class IDpm(IntEnum):  # Index proc's & module's & daugther
    # proc's in status
    parsing = 10
    logic = 11
    network = 12
    network_sim = 12
    monitoring = 13
    # module's in status
    parsing_agent = 0
    parsing_daugther = 1
    logic_agent = 2
    logic_daugther = 3
    network_agent = 4
    network_daugther = 5
    network_sim_agent = 6
    network_sim_daugther = 7
    # proc's col in profilling
    parsing_col = 0
    logic_col = 1
    network_col = 2
    network_sim_col = 2


class ProcsDictTyping(TypedDict):
    name: str
    func: FunctionType | None
    proc: Process | None


@dataclass
class ProcsCfg:
    procs: dict[int, ProcsDictTyping] = {
        IDpm.parsing: {"name": "PARSING", "func": None, "proc": None},
        IDpm.logic: {"name": "LOGIC", "func": None, "proc": None},
        IDpm.network: {"name": "NETWORK", "func": None, "proc": None},
        IDpm.monitoring: {"name": "MONITORING", "func": None, "proc": None},
    }

    # BACKTESTING False | 12: ... "func": run_wss ...}
    # BACKTESTING True | 12: ... "func": run_wss_sim ...}


@dataclass
class Config:
    """
    Configs: User | ShM's | Proc's | Array's | Path's | Other's
    """

    @dataclass
    class UserConfig:
        wss: str = "wss://fstream.binance.com/ws/"
        rest: str = "https://fapi.binance.com/"
        symbol: str = "dashusdt"
        backtesting: bool = True

    @dataclass
    class CorePath:
        profiling_bin = "dump/profiling.bin"
        profiling_csv = "dump/profiling.csv"
        pheaders_csv = "dump/pheaders.csv"
        status_json = "status_code.json"
        data_csv = "data/aggtrades.csv"

    @dataclass
    class CoreConfig:
        @dataclass
        class Grid:
            interval_min: int = 1
            # Array
            lines: int = 10000  # 10000 # + 8 lines headers
            cols: int = 4
            type_size: int = 8  # Float64
            # ShM
            shm_size: int = (((lines * cols * type_size) // 4096) + 1) * 4096
            shm_name: str = "footprint_shm_for_grid"

        @dataclass
        class Profiling:
            offset: int = 128  # for headers cols 0-64 & 64-128 other info
            # Array
            lines: int = 5000
            cols: int = 3
            type_size: int = 8
            # ShM
            shm_size: int = (((lines * cols * type_size + offset) // 4096) + 1) * 4096
            shm_name: str = "profiling_shm_for_profiling"

        @dataclass
        class Raw:
            # Double Buffer
            cell_amount: int = 256
            data_size: int = 256
            header_size: int = 2
            offset_flag: int = -1
            # ShM
            shm_size: int = (
                (((cell_amount * data_size) + (cell_amount * header_size)) * 2 // 4096)
                + 1
            ) * 4096
            shm_name: str = "raw_data_shm_for_raw_data"

        @dataclass
        class Metrics:
            # Offset's
            base_price_and_timestamp: tuple[int, int] = (0, 8 * 2)  # [a: a+b*2] int64=8
            price: tuple[int, int] = (16, 16 + (8 * 1))  # [a: a+b*1] float64=8
            tick_size: tuple[int, int] = (24, 24 + (8 * 1))  # [a: a+b*1] float64=8
            coord_offset: tuple[int, int] = (32, 32 + (2 * 6))  # [a: a+b*6] int16=2
            # Index's
            flag: int = 0
            # ShM
            shm_size: int = (coord_offset[1] // 4096 + 1) * 4096
            shm_name: str = "metrics_shm_for_different_metrics"

        @dataclass
        class Status:
            parsing = {
                "p": IDpm.parsing,
                "m": IDpm.parsing_agent,
                "d": IDpm.parsing_daugther,
                "dgc": IDpm.parsing_col,
            }
            logic = {
                "p": IDpm.logic,
                "m": IDpm.logic_agent,
                "d": IDpm.logic_daugther,
                "dgc": IDpm.logic_col,
            }
            network = {
                "p": IDpm.network,
                "m": IDpm.network_agent,
                "d": IDpm.network_daugther,
                "dgc": IDpm.network_col,
            }
            network_sim = {
                "p": IDpm.network_sim,
                "m": IDpm.network_sim_agent,
                "d": IDpm.network_sim_daugther,
                "dgc": IDpm.network_sim_col,
            }
            # ShM
            shm_size: int = (4096 // 4096 + 1) * 4096
            shm_name: str = "status_shm_for_status_procs_and_modules"

        shms_cfg: dict = {
            Grid.__name__: {Grid.shm_name: Grid.shm_size},
            Raw.__name__: {Raw.shm_name: Raw.shm_size},
            Status.__name__: {Status.shm_name: Status.shm_size},
            Metrics.__name__: {Metrics.shm_name: Metrics.shm_size},
            Profiling.__name__: {Profiling.shm_name: Profiling.shm_size},
        }
