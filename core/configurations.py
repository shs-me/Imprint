from abc import ABC

from .settings import BacktestingMode, BarHeaders, ChartInterval, SpaceCoords

UBYTE = 1
INT64 = 8
FLOAT64 = 8
OFFSET = 0


class Configuration(ABC):
    pass


# Configuration Subclasses
class ConfigurationSHMSegments(Configuration):
    pass


class ConfigurationBacktesting(Configuration):
    def __init__(
        self,
        symbol: str = "dashusdt",
        tick_size: str = "0.01",
        lot_size: str = "0.001",
        backtesting: bool = True,
        mode: BacktestingMode = BacktestingMode.ZERO_SLEEP,
    ) -> None:
        self.symbol: str = symbol
        self.tick_size: str = tick_size
        self.lot_size: str = lot_size
        self.backtesting: bool = backtesting
        self.mode = mode


# ShmSegmentsSubclasses


class ConfigurationStrategy(ConfigurationSHMSegments):
    def __init__(self) -> None:
        self.cell_amount = 128

        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.reader = OFFSET, OFFSET + INT64
        self.writer = self.reader[1], self.reader[1] + INT64
        self.price = self.writer[1], self.writer[1] + INT64
        self.qty = self.price[1], self.price[1] + INT64
        self.side = self.qty[1], self.qty[1] + UBYTE
        self.type_order = self.side[1], self.side[1] + UBYTE
        self.signal_size = self.type_order[1]
        self.signal_buf_size = self.signal_size * self.cell_amount

        self.pattern_1 = 0, self.signal_buf_size
        self.pattern_2 = self.pattern_1[1], self.signal_buf_size

        return 1


class ConfigurationFootprint(ConfigurationSHMSegments):
    def __init__(
        self,
        chart_interval: ChartInterval = ChartInterval._5M,
        chart_range: int = 1,
    ) -> None:
        self.intervalMs = chart_interval
        self.bar_count = self.get_bar_count(day=chart_range)
        self.fpLines = 10001
        self.fpCols = self.bar_count * 2
        self.fpPanelCols = self.fpCols + self.get_panel_count_cols()
        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_panel_count_cols(self) -> int:
        self.colVP, self.colDP = -2, -1
        return 2

    def get_bar_count(self, day: int) -> int:
        dayMs, ivlMs = (day if day >= 1 else 1) * 24 * 60 * 60 * 1000, self.intervalMs
        return (dayMs // ivlMs) if (dayMs > ivlMs) else (ivlMs // dayMs)

    def get_need_shm_size(self) -> int:
        self.footprint = OFFSET, OFFSET + (self.fpLines * self.fpPanelCols * INT64)
        self.headers = (
            self.footprint[1],
            self.footprint[1] + (BarHeaders._HeadersCount * self.bar_count * INT64),
        )
        self.space = (
            self.headers[1],
            self.headers[1] + (SpaceCoords._CoordsCount * 2 * INT64),
        )
        self.basePrice = self.space[1], self.space[1] + INT64
        self.baseTimestamp = self.basePrice[1], self.basePrice[1] + INT64

        self.flag = self.baseTimestamp[1]
        self.spare_flag = self.flag + UBYTE
        return self.spare_flag


class ConfigurationRingRawBuf(ConfigurationSHMSegments):
    def __init__(self) -> None:
        self.header_size = 1
        self.data_size = 256
        self.cell_amount = 10000
        self.safe_lag = int(self.cell_amount * 0.9)
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
        return self.status[1]
