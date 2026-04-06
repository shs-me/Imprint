from enum import IntEnum
from multiprocessing.synchronize import Event, Semaphore
from typing import Protocol


class CoreResources(Protocol):
    parsing_event: Event
    logic_event: Event
    general_event: Event
    sc_sem: Semaphore


class Config:
    """
    Configs: User | ShM's | Proc's | Array's | Path's | Other's
    """

    class UserConfig:
        wss: str = "wss://fstream.binance.com/ws/"
        rest: str = "https://fapi.binance.com/"
        symbol: str = "dashusdt"
        tick_size: str = "0.01"
        lot_size: str = "0.001"
        interval_min: int = 1
        backtesting: bool = True

    class CorePath:
        dirs = ["plugins", "dump", "data", "logs"]
        core_log = "logs/core_&_watchdog.log"
        profiling_log = "logs/profiling.log"
        data_csv = "data/aggtrades.csv"
        algoritm_path = "plugins/algorithm.py"
        exc_info = "dump/exc_info.log"
        profiling_bin = "dump/profiling.bin"
        profiling_csv = "dump/profiling.csv"
        pheaders_csv = "dump/pheaders.csv"

    class ShmSharing:
        class Raw:
            cell_amount, header_size, data_size = 10000, 1, 256
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
            shm_size: int = ((data_offset[1] // 4096) + 1) * 4096

        class Footprint:
            int64, float64 = 8, 8
            lines, cols = 10000, 10
            footprint: tuple[int, int] = 0, (lines * cols * int64)
            headers_count = 8
            headers = footprint[1], footprint[1] + (headers_count * int64 * (cols // 2))

            class Headers(IntEnum):
                Open, High, Low, Close = 0, 1, 2, 3
                Time, Volume, Delta, CountTrade = 4, 5, 6, 7

            coords_count = 6
            """idy_min, idx_min, idy_max, idx_max, idy, idx"""
            coord1: tuple[int, int] = headers[1], headers[1] + (coords_count * int64)
            coord2: tuple[int, int] = coord1[1], coord1[1] + (coords_count * int64)
            nBasePrice: tuple[int, int] = coord2[1], coord2[1] + int64
            nBaseTimestamp: tuple[int, int] = nBasePrice[1], nBasePrice[1] + int64
            # Index's
            flag: int = nBaseTimestamp[1]
            shm_size: int = ((flag // 4096) + 1) * 4096

        class Metrics:
            int64, float64 = 8, 8
            tick_size: tuple[int, int] = 0, int64
            lot_size: tuple[int, int] = tick_size[1], tick_size[1] + int64
            pricePrecision: tuple[int, int] = lot_size[1], lot_size[1] + int64
            qtyPrecision: tuple[int, int] = pricePrecision[1], pricePrecision[1] + int64
            shm_size: int = ((qtyPrecision[1] // 4096) + 1) * 4096

        class Monitoring:
            offset, int64 = 256, 8
            status = 0, offset
            id_error = 255
            shm_size: int = (status[1] // 4096 + 1) * 4096


class ShmBufOffset:
    __cfg = Config.ShmSharing
    raw = 0, __cfg.Raw.shm_size
    footprint = raw[1], raw[1] + __cfg.Footprint.shm_size
    metrics = footprint[1], footprint[1] + __cfg.Metrics.shm_size
    monitoring = metrics[1], metrics[1] + __cfg.Monitoring.shm_size

    shm_size = monitoring[1]
    shm_name = "GridCore"
