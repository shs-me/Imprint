from abc import ABC
from typing import Any

from .settings import BarHeaders, SpaceCoords, Timeframe

OFFSET = 0
UBYTE = 1
INT64 = 8
FLOAT64 = 8


class BaseRingBuf(ABC):
    def __init__(
        self,
        data_size: int = 1024,
        data_header_size: int = 8,
        cell_amount: int = 10_000,
    ) -> None:
        self.data_size: int = data_size
        self.data_header_size: int = data_header_size
        self.cell_amount: int = cell_amount

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
            (self.cell_amount * self.data_header_size) + self.data[1],
        )
        return self.data_header[1]


class Configuration(ABC):
    pass


class cfgBacktesting(Configuration):
    def __init__(
        self,
        balance: float = 100.0,
        min_order_size: float = 5.0,
        taker_commission: float = 0.005,
        maker_commission: float = 0.002,
        backtest_start_date: str = "2026-01-01",
        backtest_end_date: str = "2026-01-01",
    ) -> None:
        self.balance: float = balance
        self.min_order_size: float = min_order_size
        self.taker_commission: float = taker_commission
        self.maker_commission: float = maker_commission
        self.backtest_start_date: str = backtest_start_date
        self.backtest_end_date: str = backtest_end_date


class cfgAccount(Configuration):
    def __init__(
        self,
        leverage: int = 20,
        max_lock_balance: float = 0.1,
        max_loss_balance: float = 0.2,
        entry_qty: float = 0.01,
        TP_dev: float = 0.05,
        SL_dev: float = 0.05,
        slippage: float = 0.0005,
        scale_prec: int = 15,
        latency_ms: int = 100,
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


class cfgCoin(Configuration):
    def __init__(self, symbol: str, tick_size: str, lot_size: str) -> None:
        self.symbol: str = symbol
        self.tick_size: str = tick_size
        self.lot_size: str = lot_size

        self.price_prec: int = (
            len(self.tick_size.split(sep=".")[-1]) if "." in self.tick_size else 0
        )
        self.qty_prec: int = (
            len(self.lot_size.split(sep=".")[-1]) if "." in self.lot_size else 0
        )
        self.price_mult: int = 10**self.price_prec
        self.qty_mult: int = 10**self.qty_prec


class cfgSHMSegments(Configuration):
    pass


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


class cfgMetrics(cfgSHMSegments):
    def __init__(
        self,
        count_procs: int = 10,
        text_size: int = 1024,
    ) -> None:
        self.count_procs: int = count_procs
        self.text_size: int = text_size
        self.shm_size: int = ((self.get_need_shm_size() // 4096) + 1) * 4096

    def get_need_shm_size(self) -> int:
        self.status: Any = OFFSET, OFFSET + ((self.count_procs * 2) * INT64)
        self.text: Any = (
            self.status[1],
            self.status[1] + (self.count_procs * self.text_size),
        )
        self.time_start_reading: Any = (
            self.text[1],
            self.text[1] + INT64,
        )
        self.trade_readed_time: Any = (
            self.time_start_reading[1],
            self.time_start_reading[1] + INT64,
        )
        self.parsing_complete: Any = (
            self.trade_readed_time[1],
            self.trade_readed_time[1] + UBYTE,
        )
        self.logic_complete: Any = (
            self.parsing_complete[1],
            self.parsing_complete[1] + UBYTE,
        )
        self.dfm_comlpete: Any = (
            self.logic_complete[1],
            self.logic_complete[1] + UBYTE,
        )
        return self.dfm_comlpete[1]


class cfgSignal(cfgSHMSegments, BaseRingBuf):
    def __init__(self) -> None:
        BaseRingBuf.__init__(self, data_size=24, data_header_size=1, cell_amount=10_000)


class cfgUserStream(cfgSHMSegments, BaseRingBuf):
    def __init__(self) -> None:
        BaseRingBuf.__init__(
            self, data_size=1024, data_header_size=8, cell_amount=10_000
        )


class cfgDataStream(cfgSHMSegments, BaseRingBuf):
    def __init__(self) -> None:
        BaseRingBuf.__init__(
            self, data_size=256, data_header_size=1, cell_amount=10_000
        )
        self.safe_lag: int = int(self.cell_amount * 0.9)
