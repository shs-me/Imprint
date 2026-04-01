from enum import IntEnum
from multiprocessing import Process
from multiprocessing.shared_memory import SharedMemory
from types import FunctionType
from typing import TypedDict


class ProcsDictTyping(TypedDict):
    name: str
    func: FunctionType
    proc: Process | None


class ShmType(TypedDict):
    shm: SharedMemory
    buf: memoryview


class IDpm(IntEnum):
    """Index proc's & module's & daugther"""

    # proc's in status
    parsing, logic, network, monitoring, network_sim = 10, 11, 12, 13, 14
    # module's in status
    parsing_agent, parsing_daugther = 0, 1
    logic_agent, logic_daugther = 2, 3
    network_agent, network_daugther = 4, 5
    network_sim_agent, network_sim_daugther = 6, 7
    # proc's col in profilling
    parsing_col, logic_col, network_col, network_sim_col = 0, 1, 2, 2


class Config:
    """
    Configs: User | ShM's | Proc's | Array's | Path's | Other's
    """

    general_sc = (0, 49)
    warn_sc = (general_sc[1] + 1, 149)
    error_sc = (warn_sc[1] + 1, 249)
    id_info: dict[IDpm, dict[IDpm, str]] = {
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

    class UserConfig:
        wss: str = "wss://fstream.binance.com/ws/"
        rest: str = "https://fapi.binance.com/"
        symbol: str = "dashusdt"
        backtesting: bool = True

    class CorePath:
        plugin_path = "algorithm/plugin.py"
        profiling_bin = "dump/profiling.bin"
        profiling_csv = "dump/profiling.csv"
        pheaders_csv = "dump/pheaders.csv"
        status_json = "status_code.json"
        data_csv = "data/aggtrades.csv"

    class CoreConfig:
        class Grid:
            lines, cols, interval_min = 10000, 10, 1
            # ShM # TypeSize=float64=8
            shm_size: int = (((lines * cols * 8) // 4096) + 1) * 4096
            shm_name: str = "footprint_shm_for_grid"

        class Profiling:
            # for headers cols 0-64 & 64-128 other info
            lines, cols, offset = 5000, 3, 128
            # ShM # TypeSize=int64=8
            shm_size: int = (((lines * cols * 8 + offset) // 4096) + 1) * 4096
            shm_name: str = "profiling_shm_for_profiling"

        class Raw:
            cell_amount, header_size, data_size = 1000, 1, 256
            safe_lag = int(cell_amount * 0.1)
            # Ring Buffer
            ncell_offset: tuple[int, int] = (0, 8 * 2)
            header_offset: tuple[int, int] = (
                ncell_offset[1],
                (cell_amount * header_size) + ncell_offset[1],
            )
            data_offset: tuple[int, int] = (
                header_offset[1],
                (cell_amount * data_size) + header_offset[1],
            )
            # ShM
            shm_size: int = ((data_offset[1] // 4096) + 1) * 4096
            shm_name: str = "raw_data_shm_for_raw_data"

        class Metrics:
            coord_lines, coord_cols = 2, 6
            # Offset's
            base_price: tuple[int, int] = (0, 8)  # float64=8
            base_timestamp: tuple[int, int] = (base_price[1], base_price[1] + 8)
            tick_size: tuple[int, int] = (base_timestamp[1], base_timestamp[1] + 8)
            price: tuple[int, int] = (tick_size[1], tick_size[1] + 8)  # float64=8
            coord_offset: tuple[int, int] = (
                price[1],
                price[1] + ((coord_cols * coord_lines) * 2),  # uint16
            )
            # Index's
            flag: int = coord_offset[1] + 1
            # ShM
            shm_size: int = ((flag // 4096) + 1) * 4096
            shm_name: str = "metrics_shm_for_different_metrics"

        class Status:
            class parsing:
                id_p, id_m = IDpm.parsing, IDpm.parsing_agent
                id_d, id_dgc = IDpm.parsing_daugther, IDpm.parsing_col

            class logic:
                id_p, id_m = IDpm.logic, IDpm.logic_agent
                id_d, id_dgc = IDpm.logic_daugther, IDpm.logic_col

            class network:
                id_p, id_m = IDpm.network, IDpm.network_agent
                id_d, id_dgc = IDpm.network_daugther, IDpm.network_col

            class network_sim:
                id_p, id_m = IDpm.network_sim, IDpm.network_sim_agent
                id_d, id_dgc = IDpm.network_sim_daugther, IDpm.network_sim_col

            # ShM
            shm_size: int = (4096 // 4096 + 1) * 4096
            shm_name: str = "status_shm_for_status_procs_and_modules"


class ShMs:
    __cfg = Config.CoreConfig
    shms: dict[str, ShmType] = {  # type: ignore
        __cfg.Grid.__name__: {},
        __cfg.Raw.__name__: {},
        __cfg.Status.__name__: {},
        __cfg.Metrics.__name__: {},
        __cfg.Profiling.__name__: {},
    }
    # For Future Update
    __shm_size = (
        (
            __cfg.Grid.shm_size
            + __cfg.Profiling.shm_size
            + __cfg.Raw.shm_size
            + __cfg.Metrics.shm_size
            + __cfg.Status.shm_size
        )
        // 4096
        + 1
    ) * 4096
    __shm_name = "GridCore"
