"""Shared memory layout and component configuration data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

from imprint.core.settings import Timeframe

PERCENT: int = 10_000

OFFSET: int = 0
UBYTE: int = 1
INT64: int = 8
FLOAT64: int = 8


@final
@dataclass(slots=True)
class Segment:
    size: int

    offset: tuple[int, int] = field(default=None, init=False)  # pyright: ignore[reportAssignmentType]
    view: memoryview = field(default=None, init=False)  # pyright: ignore[reportAssignmentType]


@final
@dataclass(slots=True)
class Percent:
    str_: str

    int_: int = field(init=False)

    def __post_init__(self) -> None:
        self.int_ = round(float(self.str_.split("%")[0]) / 100 * PERCENT)


@dataclass
class Configuration(ABC):
    """Abstract base class for engine configuration objects."""

    pass


@final
@dataclass(slots=True)
class Setup(Configuration):
    backtesting: bool = True
    execution: bool = True
    backtest_start_date: str = "2026-01-01"
    backtest_end_date: str = "2026-01-01"
    algorithm_module: str = ""
    algorithm_class_name: str = ""
    execution_module: str = ""
    execution_class_name: str = ""
    agg_trades_decoder_module: str = ""
    agg_trades_decoder_class_name: str = ""
    user_stream_decoder_module: str = ""
    user_stream_decoder_class_name: str = ""
    order_encoder_module: str = ""
    order_encoder_class_name: str = ""


@final
@dataclass(slots=True)
class Connector(Configuration):
    base_uri_for_rest: str = ""
    base_uri_for_ws: str = ""
    base_uri_for_wss: str = ""
    market_data_uri_for_wss: str = ""
    get_user_data_uri_for_wss: str = ""
    set_user_data_uri_for_wss: str = ""


@final
@dataclass(slots=True)
class Account(Configuration):
    leverage: int = 20
    balance: float = 100.0
    min_order_size: float = 5.0
    taker_commission: Percent = field(default_factory=lambda: Percent("0.05%"))
    maker_commission: Percent = field(default_factory=lambda: Percent("0.02%"))
    slippage: Percent = field(default_factory=lambda: Percent("0.05%"))
    latency_ms: int = 100
    scale_prec: int = 15
    active_order_limit: int = 1000
    save_orders_history: bool = False

    scale_mult: int = field(init=False)

    def __post_init__(self) -> None:
        self.scale_mult = 10**self.scale_prec


@final
@dataclass(slots=True)
class RiskManagment(Configuration):
    max_lock_balance: Percent = field(default_factory=lambda: Percent("10%"))
    max_loss_balance: Percent = field(default_factory=lambda: Percent("10%"))
    entry_qty: Percent = field(default_factory=lambda: Percent("1%"))
    tp_dev: Percent = field(default_factory=lambda: Percent("5%"))
    sl_dev: Percent = field(default_factory=lambda: Percent("5%"))
    pass_signal_if_analysis_time_big: int = 50_000
    pass_execute_signal_if_timer_ms_exepired: int = 1_000


@final
@dataclass(slots=True)
class Coin(Configuration):
    symbol: str = "DASHUSDT"
    tick_size: str = "0.01"
    lot_size: str = "0.001"

    @property
    def price_prec(self) -> int:
        return (
            len(self.tick_size.split(sep=".")[-1])
            if "." in self.tick_size
            else 0
        )

    @property
    def qty_prec(self) -> int:
        return (
            len(self.lot_size.split(sep=".")[-1]) if "." in self.lot_size else 0
        )

    @property
    def price_mult(self) -> int:
        return 10**self.price_prec

    @property
    def qty_mult(self) -> int:
        return 10**self.qty_prec


@final
@dataclass(slots=True)
class Footprint(Configuration):
    timeframe: Timeframe = Timeframe.H1
    chart_range: int = 1
    step_tick: int = 1
    fp_rows: int = 10001
    save_fp_headers: bool = False

    colVP: int = field(init=False)
    colDP: int = field(init=False)
    bar_count: int = field(init=False)
    fp_cols: int = field(init=False)
    fp_panel_cols: int = field(init=False)

    def __post_init__(self) -> None:
        self.colVP = -2
        self.colDP = -1
        self.bar_count = self._get_bar_count(day=self.chart_range)
        self.fp_cols = self.bar_count * 2
        self.fp_panel_cols = self.fp_cols + 2

    def _get_bar_count(self, day: int) -> int:
        dayMs: int = (day if day >= 1 else 1) * 24 * 60 * 60 * 1000
        ivlMs: int = self.timeframe
        return (dayMs // ivlMs) if (dayMs > ivlMs) else (ivlMs // dayMs)


@dataclass(slots=True)
class SharedMemorySegments(Configuration, ABC):
    shm_size: int = 0

    def __post_init__(self) -> None:
        self._set_attr_use_shm()
        self.shm_size = ((self.__get_need_shm_size() // 4096) + 1) * 4096

    @abstractmethod
    def _set_attr_use_shm(self) -> None:
        pass

    @final
    def __get_need_shm_size(self) -> int:
        offset: int = 0
        for attr_name in self.__slots__:
            attr_obj = getattr(self, attr_name)
            if isinstance(attr_obj, Segment):
                attr_obj.offset = (
                    offset,
                    (offset := (offset + attr_obj.size)),
                )

        return offset


@final
@dataclass(slots=True)
class Metrics(SharedMemorySegments):
    count_procs: int = 10

    procs_status: Segment = field(init=False)
    main_status: Segment = field(init=False)
    time_start_reading: Segment = field(init=False)
    trade_readed_time: Segment = field(init=False)
    engine_complete: Segment = field(init=False)

    @override
    def _set_attr_use_shm(self) -> None:
        self.procs_status = Segment((self.count_procs * 2) * INT64)
        self.main_status = Segment(self.count_procs * INT64)
        self.time_start_reading = Segment(INT64)
        self.trade_readed_time = Segment(INT64)
        self.engine_complete = Segment(UBYTE)


@dataclass
class BaseRingBuf(ABC):
    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 10_000
    count_writer: int = 1
    count_reader: int = 1

    safe_lag: int = field(init=False)

    reader_id: Segment = field(init=False)
    writer_id: Segment = field(init=False)
    data: Segment = field(init=False)
    data_header: Segment = field(init=False)

    def _set_attr_use_shm(self) -> None:
        self.safe_lag = int(self.cell_amount * 0.9)

        self.reader_id = Segment(self.count_reader * INT64)
        self.writer_id = Segment(self.count_writer * INT64)
        self.data = Segment(
            self.count_writer * (self.cell_amount * self.data_size)
        )
        self.data_header = Segment(
            self.count_writer * (self.cell_amount * self.data_header_size)
        )


@dataclass(slots=True)
class TextStream(BaseRingBuf, SharedMemorySegments):
    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 100
    count_reader: int = 10
    count_writer: int = 10


@dataclass(slots=True)
class Signal(BaseRingBuf, SharedMemorySegments):
    data_size: int = 32
    data_header_size: int = 1
    cell_amount: int = 1000


@dataclass(slots=True)
class GetUserStream(BaseRingBuf, SharedMemorySegments):
    data_size: int = 128
    data_header_size: int = 1
    cell_amount: int = 1000


@dataclass(slots=True)
class SetUserStream(BaseRingBuf, SharedMemorySegments):
    data_size: int = 128
    data_header_size: int = 1
    cell_amount: int = 1000


@dataclass(slots=True)
class DataStream(BaseRingBuf, SharedMemorySegments):
    data_size: int = 256
    data_header_size: int = 1
    cell_amount: int = 10_000
