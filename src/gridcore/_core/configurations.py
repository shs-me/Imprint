from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .settings import BarHeaders, SpaceCoords, Timeframe

OFFSET = 0
UBYTE = 1
INT64 = 8
FLOAT64 = 8


class Configuration(ABC):
    pass

    def percent_to_int(self) -> None:
        for name, value in self.__dict__.items():
            if isinstance(value, str):
                setattr(self, name, round(float(value.split("%")[0]) / 100 * 10_000))


@dataclass
class Setup(Configuration):
    backtesting: bool = True
    execution: bool = True
    backtest_start_date: str = "2026-01-01"
    backtest_end_date: str = "2026-01-01"


@dataclass
class Account(Configuration):
    leverage: int = 20
    balance: float = 100.0
    min_order_size: float = 5.0
    taker_commission: Any = "0.05%"
    maker_commission: Any = "0.02%"
    slippage: Any = "0.05%"
    latency_ms: Any = 100
    scale_prec: Any = 15
    analysis_safe_lag_microsecond: int = 50_000
    save_orders_history: bool = False

    def __post_init__(self) -> None:
        self.percent_to_int()
        self.scale_mult = 10**self.scale_prec


@dataclass
class Strategy(Configuration):
    max_lock_balance: Any = "10%"
    max_loss_balance: Any = "10%"
    entry_qty: Any = "1%"
    tp_dev: Any = "5%"
    sl_dev: Any = "5%"
    timer_signal: int = 1000

    def __post_init__(self):
        self.percent_to_int()


@dataclass
class Coin(Configuration):
    symbol: str = "DASHUSDT"
    tick_size: str = "0.01"
    lot_size: str = "0.001"

    def __post_init__(self) -> None:
        self.price_prec: int = (
            len(self.tick_size.split(sep=".")[-1]) if "." in self.tick_size else 0
        )
        self.qty_prec: int = (
            len(self.lot_size.split(sep=".")[-1]) if "." in self.lot_size else 0
        )
        self.price_mult: int = 10**self.price_prec
        self.qty_mult: int = 10**self.qty_prec


@dataclass
class SharedMemorySegments(Configuration, ABC):
    shm_size: int = 0

    def __post_init__(self) -> None:
        self.shm_size = ((self.get_need_shm_size() // 4096) + 1) * 4096

    @abstractmethod
    def get_need_shm_size(self) -> int:
        pass


@dataclass
class Footprint(SharedMemorySegments):
    timeframe: Timeframe = Timeframe._H
    chart_range: int = 1
    fp_rows: int = 10001
    save_fp_headers: bool = False
    save_algorithm_metadata: bool = False
    algorithm_module: str = ""
    algorithm_class_name: str = ""

    def _init_data(self) -> None:
        self.colVP, self.colDP = -2, -1
        self.bar_count: int = self.get_bar_count(day=self.chart_range)
        self.fp_cols: int = self.bar_count * 2
        self.fp_panel_cols: int = self.fp_cols + 2

    def get_bar_count(self, day: int) -> int:
        dayMs, ivlMs = (
            (day if day >= 1 else 1) * 24 * 60 * 60 * 1000,
            self.timeframe,
        )
        return (dayMs // ivlMs) if (dayMs > ivlMs) else (ivlMs // dayMs)

    def get_need_shm_size(self) -> int:
        self._init_data()

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


@dataclass
class Metrics(SharedMemorySegments):
    count_procs: int = 10
    text_size: int = 1024

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
        return self.logic_complete[1]


@dataclass
class BaseRingBuf(ABC):
    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 10_000

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


@dataclass
class Signal(BaseRingBuf, SharedMemorySegments):
    data_size: int = 24
    data_header_size: int = 1
    cell_amount: int = 10_000


@dataclass
class UserStream(BaseRingBuf, SharedMemorySegments):
    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 10_000


@dataclass
class DataStream(BaseRingBuf, SharedMemorySegments):
    data_size: int = 256
    data_header_size: int = 1
    cell_amount: int = 10_000

    def __post_init__(self) -> None:
        super().__post_init__()
        self.safe_lag: int = int(self.cell_amount * 0.9)
