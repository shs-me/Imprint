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
    parsing = 10
    logic = 11
    network = 12
    network_sim = 14
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


class Config:
    """
    Configs: User | ShM's | Proc's | Array's | Path's | Other's
    """

    class UserConfig:
        wss: str = "wss://fstream.binance.com/ws/"
        rest: str = "https://fapi.binance.com/"
        symbol: str = "dashusdt"
        backtesting: bool = True

    class CorePath:
        profiling_bin = "dump/profiling.bin"
        profiling_csv = "dump/profiling.csv"
        pheaders_csv = "dump/pheaders.csv"
        status_json = "status_code.json"
        data_csv = "data/aggtrades.csv"

    class CoreConfig:
        class Grid:
            interval_min: int = 1
            # Array
            lines: int = 10000  # 10000 # + 8 lines headers
            cols: int = 4
            type_size: int = 8  # Float64
            # ShM
            shm_size: int = (((lines * cols * type_size) // 4096) + 1) * 4096
            shm_name: str = "footprint_shm_for_grid"

        class Profiling:
            offset: int = 128  # for headers cols 0-64 & 64-128 other info
            # Array
            lines: int = 5000
            cols: int = 3
            type_size: int = 8
            # ShM
            shm_size: int = (((lines * cols * type_size + offset) // 4096) + 1) * 4096
            shm_name: str = "profiling_shm_for_profiling"

        class Raw:
            # Double Buffer
            cell_amount: int = 256
            data_size: int = 256
            header_size: int = 1
            flag: int = -1
            # ShM
            shm_size: int = (
                (((cell_amount * data_size) + (cell_amount * header_size)) * 2 // 4096)
                + 1
            ) * 4096
            shm_name: str = "raw_data_shm_for_raw_data"

        class Metrics:
            # Offset's
            base_price_and_timestamp: tuple[int, int] = (0, 8 * 2)  # [a: a+b*2] int64=8
            price: tuple[int, int] = (16, 16 + (8 * 1))  # [a: a+b*1] float64=8
            tick_size: tuple[int, int] = (24, 24 + (8 * 1))  # [a: a+b*1] float64=8
            coord_buf1: tuple[int, int] = (32, 32 + (2 * 6))  # [a: a+b*6] int16=2
            coord_buf2: tuple[int, int] = (44, 44 + (2 * 6))  # [a: a+b*6] int16=2
            # Index's
            flag: int = 56
            # ShM
            shm_size: int = (coord_buf2[1] // 4096 + 1) * 4096
            shm_name: str = "metrics_shm_for_different_metrics"

        class Status:
            class parsing:
                id_p: int = IDpm.parsing
                id_m: int = IDpm.parsing_agent
                id_d: int = IDpm.parsing_daugther
                id_dgc: int = IDpm.parsing_col

            class logic:
                id_p: int = IDpm.logic
                id_m: int = IDpm.logic_agent
                id_d: int = IDpm.logic_daugther
                id_dgc: int = IDpm.logic_col

            class network:
                id_p: int = IDpm.network
                id_m: int = IDpm.network_agent
                id_d: int = IDpm.network_daugther
                id_dgc: int = IDpm.network_col

            class network_sim:
                id_p: int = IDpm.network_sim
                id_m: int = IDpm.network_sim_agent
                id_d: int = IDpm.network_sim_daugther
                id_dgc: int = IDpm.network_sim_col

            # ShM
            shm_size: int = (4096 // 4096 + 1) * 4096
            shm_name: str = "status_shm_for_status_procs_and_modules"
