from abc import ABC

from .settings import ChartInterval, ClusterHeaders, SpaceCoords

UBYTE = 1
INT64 = 8
FLOAT64 = 8
OFFSET = 0


class Configuration(ABC):
    pass


# Configuration Subclasses
class ConfigurationStrategies(Configuration):
    pass


class ConfigurationSHMSegments(Configuration):
    pass


class ConfigurationBacktesting(Configuration):
    def __init__(
        self,
        symbol: str = "dashusdt",
        tick_size: str = "0.01",
        lot_size: str = "0.001",
        backtesting: bool = True,
    ) -> None:
        self.symbol: str = symbol
        self.tick_size: str = tick_size
        self.lot_size: str = lot_size
        self.backtesting: bool = backtesting


# ShmSegmentsSubclasses
class ConfigurationFootprint(ConfigurationSHMSegments):
    def __init__(
        self,
        chart_interval: ChartInterval = ChartInterval._H,
        chart_range: int = 1,
    ) -> None:
        self.intervalMs = chart_interval
        self.cluster_count = self.get_cluster_count(day=chart_range)
        self.lines = 10000
        self.footprintCols = self.cluster_count * 2
        self.panelCols = self.footprintCols + self.get_panel_count_cols()
        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_panel_count_cols(self) -> int:
        self.colVP, self.colBidVP, self.colAskVP = -3, -2, -1
        return 3

    def get_cluster_count(self, day: int) -> int:
        dayMs, ivlMs = (day if day >= 1 else 1) * 24 * 60 * 60 * 1000, self.intervalMs
        return (dayMs // ivlMs) if (dayMs > ivlMs) else (ivlMs // dayMs)

    def get_need_shm_size(self) -> int:
        self.footprint: tuple[int, int] = OFFSET, (self.lines * self.panelCols * INT64)
        self.headers = (
            self.footprint[1],
            self.footprint[1]
            + (ClusterHeaders._HeadersCount * self.cluster_count * INT64),
        )
        self.space_1 = (
            self.headers[1],
            self.headers[1] + (SpaceCoords._CoordsCount * INT64),
        )
        self.space_2 = (
            self.space_1[1],
            self.space_1[1] + (SpaceCoords._CoordsCount * INT64),
        )
        self.basePrice = self.space_2[1], self.space_2[1] + INT64
        self.baseTimestamp = self.basePrice[1], self.basePrice[1] + INT64

        self.flag = self.baseTimestamp[1]
        self.flag_spare = self.flag
        return self.flag_spare


class ConfigurationExecution(ConfigurationSHMSegments):
    def __init__(self, count_symbols: int = 1) -> None:
        self.countSymbols = count_symbols
        self.countSignals = 100
        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        # every signals buf size
        self.signalsSize = (UBYTE + UBYTE + INT64) * self.countSignals
        # Signals data
        self.sellSide = OFFSET
        self.buySide = self.sellSide + UBYTE
        self.nPrice = self.buySide, self.buySide + INT64
        # sum signals buf each symbols
        self.signals = (
            OFFSET,
            OFFSET + (self.signalsSize * self.countSymbols),
        )
        return self.signals[1]


class ConfigurationRingRawBuf(ConfigurationSHMSegments):
    def __init__(self) -> None:
        self.header_size = 1
        self.data_size = 256
        self.cell_amount = 10000
        self.safe_lag = int(self.cell_amount * 0.1)
        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.ReaderCellCounter = OFFSET, OFFSET + INT64
        self.WriterCellCounter = (
            self.ReaderCellCounter[1],
            self.ReaderCellCounter[1] + INT64,
        )
        self.dataHeader = (
            self.WriterCellCounter[1],
            (self.cell_amount * self.header_size) + self.WriterCellCounter[1],
        )
        self.data = (
            self.dataHeader[1],
            (self.cell_amount * self.data_size) + self.dataHeader[1],
        )
        return self.data[1]


class ConfigurationMetrics(ConfigurationSHMSegments):
    def __init__(self) -> None:
        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.tick_size = OFFSET, OFFSET + INT64
        self.lot_size = self.tick_size[1], self.tick_size[1] + INT64
        self.pricePrecision = self.lot_size[1], self.lot_size[1] + INT64
        self.qtyPrecision = self.pricePrecision[1], self.pricePrecision[1] + INT64
        self.time_to_sleep = self.qtyPrecision[1], self.qtyPrecision[1] + INT64
        return self.time_to_sleep[1]


class ConfigurationMonitoring(ConfigurationSHMSegments):
    def __init__(self) -> None:
        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.status = 0, 256
        self.id_error = 255
        return self.id_error
