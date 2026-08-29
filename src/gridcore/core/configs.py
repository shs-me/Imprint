"""Shared memory layout and component configuration data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import override

from .settings import Timeframe

PERCENT: int = 10_000

OFFSET: int = 0
UBYTE: int = 1
INT64: int = 8
FLOAT64: int = 8


@dataclass
class AggTradesStructFieldsNames:
    price: str = ""
    qty: str = ""
    timestamp: str = ""
    is_sell: str = ""


@dataclass
class OrderStructFieldsNames:
    order_id: str = ""
    type_place: str = ""
    param: str = ""
    symbol: str = ""
    side: str = ""
    type: str = ""
    timeInForce: str = ""
    quantity: str = ""
    timestamp: str = ""
    price: str = ""


@dataclass
class Segment:
    size: int

    offset: tuple[int, int] = field(init=False)
    view: memoryview = field(init=False)

    def __getitem__(self, data: tuple[int, int] | memoryview) -> None:
        if isinstance(data, tuple):
            self.offset = data
        else:
            self.view = data


@dataclass
class Percent:
    str_: str

    int_: int = field(init=False)

    def __post_init__(self) -> None:
        self.int_ = round(float(self.str_.split("%")[0]) / 100 * PERCENT)


class Configuration(ABC):
    """Abstract base class for engine configuration objects."""

    pass


@dataclass
class Setup(Configuration):
    backtesting: bool = True
    execution: bool = True
    backtest_start_date: str = "2026-01-01"
    backtest_end_date: str = "2026-01-01"
    algorithm_module: str = ""
    algorithm_class_name: str = ""
    execution_module: str = ""
    execution_class_name: str = ""
    agg_trades_struct_fields_names: AggTradesStructFieldsNames = (
        AggTradesStructFieldsNames()
    )
    user_stream_decoder_module: str = ""
    user_stream_decoder_class_name: str = ""
    order_encoder_struct_fields_names: OrderStructFieldsNames = OrderStructFieldsNames()


@dataclass
class Connector(Configuration):
    base_uri_for_rest: str = ""
    base_uri_for_ws: str = ""
    base_uri_for_wss: str = ""
    market_data_uri_for_wss: str = ""
    get_user_data_uri_for_wss: str = ""
    set_user_data_uri_for_wss: str = ""


@dataclass
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


@dataclass
class RiskManagment(Configuration):
    max_lock_balance: Percent = field(default_factory=lambda: Percent("10%"))
    max_loss_balance: Percent = field(default_factory=lambda: Percent("10%"))
    entry_qty: Percent = field(default_factory=lambda: Percent("1%"))
    tp_dev: Percent = field(default_factory=lambda: Percent("5%"))
    sl_dev: Percent = field(default_factory=lambda: Percent("5%"))
    pass_signal_if_analysis_time_big: int = 50_000
    pass_execute_signal_if_timer_ms_exepired: int = 1_000


@dataclass
class Coin(Configuration):
    symbol: str = "DASHUSDT"
    tick_size: str = "0.01"
    lot_size: str = "0.001"

    @property
    def price_prec(self) -> int:
        return len(self.tick_size.split(sep=".")[-1]) if "." in self.tick_size else 0

    @property
    def qty_prec(self) -> int:
        return len(self.lot_size.split(sep=".")[-1]) if "." in self.lot_size else 0

    @property
    def price_mult(self) -> int:
        return 10**self.price_prec

    @property
    def qty_mult(self) -> int:
        return 10**self.qty_prec


@dataclass
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


@dataclass
class SharedMemorySegments(Configuration, ABC):
    """Abstract base class for shared memory offset calculation and segment management."""

    shm_size: int = 0

    def __post_init__(self) -> None:
        """Triggers shared memory attribute initialization and page-aligned size calculation."""

        self._set_attr_use_shm()
        self.shm_size = ((self.__get_need_shm_size() // 4096) + 1) * 4096

    @abstractmethod
    def _set_attr_use_shm(self) -> None:
        """Abstract method to specify attributes occupying shared memory space."""

        pass

    def __get_need_shm_size(self) -> int:
        offset: int = 0
        for _attr_name, attr_obj in self.__dict__.items():
            if isinstance(attr_obj, Segment):
                attr_obj[(offset, (offset := (offset + attr_obj.size)))]

        return offset


@dataclass
class Metrics(SharedMemorySegments):
    """Shared memory layout for inter-process synchronization metrics and status flags."""

    count_procs: int = 10

    @override
    def _set_attr_use_shm(self) -> None:
        """Allocates shared memory offsets for process status codes, timestamps, and text buffers."""

        self.procs_status: Segment = Segment((self.count_procs * 2) * INT64)
        self.main_status: Segment = Segment(self.count_procs * INT64)
        self.time_start_reading: Segment = Segment(INT64)
        self.trade_readed_time: Segment = Segment(INT64)
        self.engine_complete: Segment = Segment(UBYTE)


@dataclass
class BaseRingBuf(ABC):
    """Base template for shared memory ring buffer memory layouts."""

    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 10_000
    count_writer: int = 1
    count_reader: int = 1

    def _set_attr_use_shm(self) -> None:
        """Allocates shared memory offsets for reader/writer head positions and data cell arrays."""

        self.reader_id: Segment = Segment(self.count_reader * INT64)
        self.writer_id: Segment = Segment(self.count_writer * INT64)
        self.data: Segment = Segment(
            self.count_writer * (self.cell_amount * self.data_size)
        )
        self.data_header: Segment = Segment(
            self.count_writer * (self.cell_amount * self.data_header_size)
        )


@dataclass
class TextStream(BaseRingBuf, SharedMemorySegments):
    "Shared memory ring buffer for procs text stream"

    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 100
    count_reader: int = 10
    count_writer: int = 10

    def __post_init__(self) -> None:
        """Initializes ring buffer parent structures and sets safe ring buffer capacity lag threshold."""
        super().__post_init__()
        self.safe_lag: int = int(self.cell_amount * 0.9)


@dataclass
class Signal(BaseRingBuf, SharedMemorySegments):
    """Shared memory ring buffer layout for strategy trade signals."""

    data_size: int = 32
    data_header_size: int = 1
    cell_amount: int = 1000

    def __post_init__(self) -> None:
        """Initializes ring buffer parent structures and sets safe ring buffer capacity lag threshold."""
        super().__post_init__()
        self.safe_lag: int = int(self.cell_amount * 0.9)


@dataclass
class GetUserStream(BaseRingBuf, SharedMemorySegments):
    """Shared memory ring buffer layout for user execution events."""

    data_size: int = 128
    data_header_size: int = 1
    cell_amount: int = 1000

    def __post_init__(self) -> None:
        """Initializes ring buffer parent structures and sets safe ring buffer capacity lag threshold."""
        super().__post_init__()
        self.safe_lag: int = int(self.cell_amount * 0.9)


@dataclass
class SetUserStream(BaseRingBuf, SharedMemorySegments):
    """Shared memory ring buffer layout for user execution events."""

    data_size: int = 128
    data_header_size: int = 1
    cell_amount: int = 1000

    def __post_init__(self) -> None:
        """Initializes ring buffer parent structures and sets safe ring buffer capacity lag threshold."""
        super().__post_init__()
        self.safe_lag: int = int(self.cell_amount * 0.9)


@dataclass
class DataStream(BaseRingBuf, SharedMemorySegments):
    """Shared memory ring buffer layout for raw tick stream ingestion."""

    data_size: int = 256
    data_header_size: int = 1
    cell_amount: int = 10_000

    def __post_init__(self) -> None:
        """Initializes ring buffer parent structures and sets safe ring buffer capacity lag threshold."""
        super().__post_init__()
        self.safe_lag: int = int(self.cell_amount * 0.9)
