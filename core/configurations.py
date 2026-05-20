from abc import ABC

from core.settings import (
    ActiveOrders,
    BarHeaders,
    ChartInterval,
    DataForMatching,
    SpaceCoords,
    TradeParam,
)

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
        tick_size: str = "0.01",
        lot_size: str = "0.001",
        minOrderSizeUSDT: float = 5.0,
        taker_commission: float = 0.005,
        maker_commission: float = 0.002,
        balanceUSDT: float = 100.0,
        dayForPrepper: int | None = None,
        startDateForPrepper: str | None = None,
        endDateForPrepper: str | None = None,
    ) -> None:
        self.tick_size: str = tick_size
        self.lot_size: str = lot_size
        self.minOrderSizeUSDT: float = minOrderSizeUSDT
        self.taker_commision: float = taker_commission
        self.maker_commission: float = maker_commission
        self.balance = balanceUSDT
        self.startDateForPrepper = startDateForPrepper
        self.endDateForPrepper = endDateForPrepper


# ShmSegmentsSubclasses
class ConfigurationStrategy(ConfigurationSHMSegments):
    def __init__(
        self,
        scalePrec: int = 20,
        leverage: int = 20,
        maxLockBalance: float = 0.1,
        maxLossBalance: float = 0.2,
        entry_qty: float = 0.01,
        TPdev: float = 0.05,
        SLdev: float = 0.05,
        slippage: float = 0.0005,
        latencyMs: int = 100,
        countOrderHistory: int = 10000,
        countActiveOrder: int = 100,
    ) -> None:
        self.scalePrec: int = scalePrec
        self.leverage: int = leverage
        self.maxLockBalance: int = round(maxLockBalance * 1000)
        self.maxLossBalance: int = round(maxLossBalance * 1000)
        self.entryQty: int = round(entry_qty * 1000)
        self.TPdev: int = round(TPdev * 1000)
        self.SLdev: int = round(SLdev * 1000)
        self.slipage: int = round(slippage * 10000)
        self.latency: int = latencyMs

        self.ordersHistoryLines: int = countOrderHistory
        self.ordersHistoryCols: int = TradeParam._ConstantCount
        self.activeOrdersLines: int = countActiveOrder
        self.activeOrdersCols: int = ActiveOrders._ConstantCount
        self.cell_amount: int = 1000

        self.shm_size: int = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.reader = OFFSET, OFFSET + INT64
        self.writer = self.reader[1], self.reader[1] + INT64
        self.offset = self.writer[1]
        self.nPrice = OFFSET, OFFSET + INT64
        self.time_ms = self.nPrice[1], self.nPrice[1] + INT64
        self.orderParam = self.time_ms[1], self.time_ms[1] + INT64
        self.orderID = self.orderParam[1], self.orderParam[1] + INT64
        self.commission = self.orderID[1], self.orderID[1] + INT64

        self.signal_size = self.orderParam[1]
        self.executed_size = self.commission[1]

        self.signal_buf_size = self.offset + self.signal_size * self.cell_amount
        self.executedBuf_size = self.offset + self.executed_size * self.cell_amount

        self.executeBuf = OFFSET, OFFSET + self.signal_buf_size
        self.executedBuf = (
            self.executeBuf[1],
            self.executeBuf[1] + self.executedBuf_size,
        )
        return self.executedBuf[1]


class ConfigurationFootprint(ConfigurationSHMSegments):
    def __init__(
        self,
        chart_interval: ChartInterval = ChartInterval._H,
        chart_range: int = 1,
        fp_lines: int = 10001,
        save_headers_as_csv: bool = False,
        analysis_safe_lag_microsecond: int = 50_000,
    ) -> None:
        self.intervalMs = chart_interval
        self.bar_count = self.get_bar_count(day=chart_range)
        self.fpLines = fp_lines
        self.save_headers = save_headers_as_csv
        self.analysis_safe_lag_microsecond = analysis_safe_lag_microsecond

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
            self.footprint[1] + (self.bar_count * BarHeaders._ConstantCount * INT64),
        )

        self.meta_data = (self.headers[1], self.headers[1] + (6 * FLOAT64))
        self.space = (
            self.meta_data[1],
            self.meta_data[1] + (SpaceCoords._ConstantCount * 2 * INT64),
        )
        self.basePrice = self.space[1], self.space[1] + INT64
        self.baseTimestamp = self.basePrice[1], self.basePrice[1] + INT64

        self.fp_shm_name = self.baseTimestamp[1], self.baseTimestamp[1] + 14
        self.flag = self.fp_shm_name[1]
        self.spare_flag = self.flag + UBYTE
        self.space_read = self.spare_flag + UBYTE
        return self.space_read


class ConfigurationRingRawBuf(ConfigurationSHMSegments):
    def __init__(self, cell_amount: int = 10000) -> None:
        self.header_size = 1
        self.data_size = 256
        self.cell_amount = cell_amount
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
    def __init__(self, dataForMatchingLines: int = 500_000) -> None:
        self.dfmLines = dataForMatchingLines
        self.dfmCols = DataForMatching._ConstantCount

        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.tick_size = OFFSET, OFFSET + INT64
        self.lot_size = self.tick_size[1], self.tick_size[1] + INT64
        self.pricePrecision = self.lot_size[1], self.lot_size[1] + INT64
        self.qtyPrecision = self.pricePrecision[1], self.pricePrecision[1] + INT64

        self.dfm_1 = (
            self.qtyPrecision[1],
            self.qtyPrecision[1] + (self.dfmLines * self.dfmCols * INT64),
        )
        self.dfm_2 = (
            self.dfm_1[1],
            self.dfm_1[1] + (self.dfmLines * self.dfmCols * INT64),
        )
        self.dfm_1_row_id = (self.dfm_2[1], self.dfm_2[1] + INT64)
        self.dfm_2_row_id = (self.dfm_1_row_id[1], self.dfm_1_row_id[1] + INT64)

        self.timeStartReading = (self.dfm_2_row_id[1], self.dfm_2_row_id[1] + INT64)
        self.tradesParsed = self.timeStartReading[1], self.timeStartReading[1] + UBYTE
        return self.tradesParsed[1]


class ConfigurationMonitoring(ConfigurationSHMSegments):
    def __init__(self) -> None:
        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.procs_buf = 0, 40 * INT64
        return self.procs_buf[1]
