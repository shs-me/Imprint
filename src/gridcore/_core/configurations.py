from abc import ABC
from typing import Any

from .settings import ActiveOrders, BarHeaders, SpaceCoords, Timeframe, TradeParam

OFFSET = 0
UBYTE = 1
INT64 = 8
FLOAT64 = 8


class Configuration(ABC):
    pass


class cfgBacktesting(Configuration):
    def __init__(
        self,
        balance: float = 100.0,
        min_order_size: float = 5.0,
        taker_commission: float = 0.005,
        maker_commission: float = 0.002,
        tick_size: str = "0.01",
        lot_size: str = "0.001",
        backtest_start_date: str = "2026-01-01",
        backtest_end_date: str = "2026-01-01",
    ) -> None:
        self.balance: float = balance
        self.min_order_size: float = min_order_size
        self.taker_commission: float = taker_commission
        self.maker_commission: float = maker_commission
        self.tick_size: str = tick_size
        self.lot_size: str = lot_size
        self.backtest_start_date: str = backtest_start_date
        self.backtest_end_date: str = backtest_end_date


class cfgSHMSegments(Configuration):
    pass


class cfgStrategy(cfgSHMSegments):
    def __init__(
        self,
        leverage: int = 20,
        max_lock_balance: float = 0.1,
        max_loss_balance: float = 0.2,
        entry_qty: float = 0.01,
        TP_dev: float = 0.05,
        SL_dev: float = 0.05,
        slippage: float = 0.0005,
        scale_prec: int = 20,
        latency_ms: int = 100,
        count_order_history: int = 10_000,
        count_active_order: int = 1000,
        analysis_safe_lag_microsecond: int = 50_000,
        save_orders_history: bool = False,
    ) -> None:
        self.leverage: int = leverage
        self.max_lock_balance: int = round(max_lock_balance * 1000)
        self.max_loss_balance: int = round(max_loss_balance * 1000)
        self.entry_qty: int = round(entry_qty * 1000)
        self.tp_dev: int = round(TP_dev * 1000)
        self.sl_dev: int = round(SL_dev * 1000)
        self.slipage: int = round(slippage * 10000)
        self.scale_prec: int = scale_prec
        self.latency: int = latency_ms
        self.analysis_safe_lag_microsecond: int = analysis_safe_lag_microsecond
        self.save_orders_history: bool = save_orders_history

        self.orders_history_rows: int = count_order_history
        self.orders_history_cols: int = TradeParam._ConstantCount
        self.active_orders_rows: int = count_active_order
        self.active_orders_cols: int = ActiveOrders._ConstantCount
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


class cfgFootprint(cfgSHMSegments):
    def __init__(
        self,
        timeframe: Timeframe = Timeframe._H,
        chart_range: int = 1,
        fp_rows: int = 10001,
        save_fp_headers: bool = False,
        save_algorithm_metadata: bool = False,
        algorithm_module: str = "",
        algorithm_package: str = "",
    ) -> None:
        self.timeframe_in_ms: Timeframe = timeframe
        self.bar_count: int = self.get_bar_count(day=chart_range)
        self.fp_rows: int = fp_rows
        self.save_fp_headers: bool = save_fp_headers
        self.save_algorithm_metadata: bool = save_algorithm_metadata
        self.algorithm_module: str = algorithm_module
        self.algorithm_package: str = algorithm_package
        self.fp_cols: int = self.bar_count * 2
        self.fp_panel_cols: int = self.fp_cols + self.get_panel_count_cols()
        self.shm_size: int = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_panel_count_cols(self) -> int:
        self.colVP, self.colDP = -2, -1
        return 2

    def get_bar_count(self, day: int) -> int:
        dayMs, ivlMs = (
            (day if day >= 1 else 1) * 24 * 60 * 60 * 1000,
            self.timeframe_in_ms,
        )
        return (dayMs // ivlMs) if (dayMs > ivlMs) else (ivlMs // dayMs)

    def get_need_shm_size(self) -> int:
        self.footprint: Any = (
            OFFSET,
            OFFSET + (self.fp_rows * self.fp_panel_cols * INT64),
        )
        self.headers: Any = (
            self.footprint[1],
            self.footprint[1] + (self.bar_count * BarHeaders._ConstantCount * INT64),
        )
        self.metadata: Any = self.headers[1], self.headers[1] + (6 * FLOAT64)
        self.space: Any = (
            self.metadata[1],
            self.metadata[1] + (SpaceCoords._ConstantCount * 2 * INT64),
        )
        self.base_price: Any = self.space[1], self.space[1] + INT64
        self.base_timestamp: Any = self.base_price[1], self.base_price[1] + INT64
        self.space_flag: Any = self.base_timestamp[1], self.base_timestamp[1] + UBYTE
        self.spare_flag: Any = self.space_flag[1], self.space_flag[1] + UBYTE
        return self.spare_flag[1]


class cfgWssRingBuf(cfgSHMSegments):
    def __init__(
        self,
        cell_amount: int = 10000,
    ) -> None:
        self.data_size: int = 256
        self.header_size: int = 1
        self.cell_amount: int = cell_amount
        self.safe_lag: int = int(self.cell_amount * 0.9)
        self.shm_size: int = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.reader_id: Any = OFFSET, OFFSET + INT64
        self.writer_id: Any = self.reader_id[1], self.reader_id[1] + INT64
        self.data: Any = (
            self.writer_id[1],
            (self.cell_amount * self.data_size) + self.writer_id[1],
        )
        self.data_header: Any = (
            self.data[1],
            (self.cell_amount * self.header_size) + self.data[1],
        )
        self.data_offset: int = self.data[0]
        self.data_header_offset: int = self.data_header[0]
        return self.data_header[1]


class cfgMetrics(cfgSHMSegments):
    def __init__(self) -> None:
        self.shm_size: int = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.status: Any = OFFSET, OFFSET + (40 * INT64)

        self.tick_size: Any = self.status[1], self.status[1] + INT64
        self.lot_size: Any = self.tick_size[1], self.tick_size[1] + INT64
        self.price_precision: Any = self.lot_size[1], self.lot_size[1] + INT64
        self.qty_precision: Any = (
            self.price_precision[1],
            self.price_precision[1] + INT64,
        )

        self.time_start_reading: Any = (
            self.qty_precision[1],
            self.qty_precision[1] + INT64,
        )
        self.parsing_complete: Any = (
            self.time_start_reading[1],
            self.time_start_reading[1] + UBYTE,
        )
        self.logic_complete: Any = (
            self.parsing_complete[1],
            self.parsing_complete[1] + UBYTE,
        )
        return self.logic_complete[1]
