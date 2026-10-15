"""Dynamic configurations and memory layouts for the project."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from decimal import Decimal
from typing import final, override

from imprint._core import constant as c
from imprint._core.settings import Timeframe
from imprint._core.utils.base_adapters import BalanceData, OrderData

PERCENT: int = 10_000

INT64: int = 8
FLOAT64: int = 8


@final
@dataclass(slots=True)
class Percent:
    """Stores a specified percentage in fractional form along with its integer counterpart. Multiplier: 10,000."""

    base: float

    fixed: int = field(init=False)

    def __post_init__(self) -> None:
        self.fixed = round(self.base / 100 * PERCENT)


@dataclass
class Configuration(ABC):
    """Abstract base class for all configurations. Used as a marker for group interactions."""


@final
@dataclass(slots=True)
class Setup(Configuration):
    """Engine parameter settings and module/class names for user adapters.
    Although passing class types directly as parameters works, IPC uses dynamic lazy loading
    based on the adapter module name and class name to prevent circular imports and serialization errors."""

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
    exchange_rest_module: str = ""
    exchange_rest_class_name: str = ""


@final
@dataclass(slots=True)
class Connector(Configuration):
    """URL endpoint settings for live mode."""

    base_rest_url: str = ""
    market_data_stream_url: str = ""
    user_data_stream_url: str = ""
    order_stream_url: str = ""


@final
@dataclass(slots=True)
class Account(Configuration):
    """Mixed settings pertaining to both the account and the trading pair.
    In live mode, only min_order_size, leverage, start balance, and scale_prec are used.
    latency_ms is used by the exchange simulator to pseudo-simulate network latency,
    and slippage is used for filling taker orders; both parameters are static."""

    leverage: int = 20
    balance: float = 100.0
    min_order_size: float = 5.0
    taker_commission: Percent = field(default_factory=lambda: Percent(0.05))
    maker_commission: Percent = field(default_factory=lambda: Percent(0.02))
    slippage: Percent = field(default_factory=lambda: Percent(0.05))
    latency_ms: int = 100
    scale_prec: int = 8
    active_order_limit: int = 1000

    @property
    def scale_mult(self) -> int:
        return 10**self.scale_prec


@final
@dataclass(slots=True)
class RiskManagement(Configuration):
    """Account-level risk control settings. The tp/sl_dev parameters are base values;
    custom deviations for each signal are specified upon signal submission.
    pass_signal_time is used in live mode to skip any signals where the timestamp of the
    first analyzed trade lags behind the current time by more than pass_signal_time.
    expiration_signal_time is used to skip all signals in the buffer that have resided there longer than expiration_signal_time."""

    max_lock_balance: Percent = field(default_factory=lambda: Percent(10))
    max_loss_balance: Percent = field(default_factory=lambda: Percent(10))
    entry_qty: Percent = field(default_factory=lambda: Percent(1))
    tp_dev: Percent = field(default_factory=lambda: Percent(5))
    sl_dev: Percent = field(default_factory=lambda: Percent(5))
    pass_signal_time: int = 60_000
    expiration_signal_time: int = 1_000


@final
@dataclass(slots=True)
class Coin(Configuration):
    """Settings for a specific trading pair. Additionally provides properties to compute tick size and lot size precisions,
    as well as multipliers based on them."""

    symbol: str = "DASHUSDT"
    tick_size: str = "0.01"
    lot_size: str = "0.001"

    def _to_prec(self, val: str) -> int:
        exp = Decimal(val).normalize().as_tuple().exponent
        if isinstance(exp, int) and exp < 0:
            return -exp
        else:
            return 0

    @property
    def price_prec(self) -> int:
        return self._to_prec(self.tick_size)

    @property
    def qty_prec(self) -> int:
        return self._to_prec(self.lot_size)

    @property
    def price_mult(self) -> int:
        return 10**self.price_prec

    @property
    def qty_mult(self) -> int:
        return 10**self.qty_prec


@dataclass(slots=True)
class Footprint(Configuration):
    """Footprint engine settings. The engine supports only 1 timeframe and 1 tick step.
    By default, the matrix covers a 1-day range; chart_range controls this parameter.
    Additional state and ctrade matrices have the same dimensions as the base matrix.
    The state clusters store footprint flags, and ctrade stores the trade count; disabled by default."""

    timeframe: Timeframe = Timeframe.H1
    chart_range: int = 1
    step_tick: int = 1
    state: bool = False
    ctrade: bool = False

    colVP: int = field(default=-2, init=False)
    colDP: int = field(default=-1, init=False)
    fp_rows: int = field(default=10001, init=False)

    @property
    def bar_count(self) -> int:
        dayMs: int = max(self.chart_range, 1) * 24 * 60 * 60 * 1000
        return max(1, dayMs // self.timeframe)

    @property
    def fp_cols(self) -> int:
        return self.bar_count * 2

    @property
    def fp_panel_cols(self) -> int:
        return self.fp_cols + 2


# - - - Configs For IPC - - -
@final
@dataclass(slots=True)
class Segment:
    """Used for dynamic segment property mapping.
    offset is assigned during initialization of a MemoryLayout subclass.
    view is assigned upon manually calling MemoryLayout.bind_memory,
    which avoids errors during process creation where subprocesses bind segments to views themselves."""

    size: int

    offset: tuple[int, int] = field(default=None, init=False)  # pyright: ignore[reportAssignmentType]
    view: memoryview = field(default=None, init=False)  # pyright: ignore[reportAssignmentType]


@final
@dataclass(slots=True)
class RingBuf:
    """The primary mechanism for inter-process data streaming in the project.
    Implemented as a ring buffer supporting multiple writers and readers, though configured by default for one writer and multiple readers.
    To function, a MemoryLayout subclass must declare a class attribute with an instance of this class.

    Parameters
    ----------
    data_size : int, default=256
        Byte size of each individual data cell.
    cell_amount : int, default=100
        Total number of cells in the ring buffer.
    count_writer : int, default=1
        Number of concurrent writer processes.
    count_reader : int, default=1
        Number of concurrent reader processes.
    cast_to_int64 : bool, default=False
        If True, casts data memory buffer view to 64-bit signed integers.

    Attributes
    ----------
    safe_lag : int
        Maximum allowable cell lag threshold before triggering safety warnings.
    reader_id : Segment
        Shared memory segment tracking reader cursor positions.
    writer_id : Segment
        Shared memory segment tracking writer cursor positions.
    data : Segment
        Shared memory segment holding raw ring buffer data.
    data_header : Segment
        Shared memory segment holding cell data length headers.
    rid_buf : memoryview
        Casted memory view for reader cursor positions.
    wid_buf : memoryview
        Casted memory view for writer cursor positions.
    data_buf : memoryview
        Casted memory view for buffer data.
    data_header_buf : memoryview
        Casted memory view for cell data headers.
    """

    data_size: int = 256
    cell_amount: int = 100
    count_writer: int = 1
    count_reader: int = 1
    cast_to_int64: bool = False

    safe_lag: int = field(init=False)

    reader_id: Segment = field(init=False)
    writer_id: Segment = field(init=False)
    data: Segment = field(init=False)
    data_header: Segment = field(init=False)

    rid_buf: memoryview = field(init=False)
    wid_buf: memoryview = field(init=False)
    data_buf: memoryview = field(init=False)
    data_header_buf: memoryview = field(init=False)

    def __post_init__(self) -> None:
        self.safe_lag = self.cell_amount - 3

        self.reader_id = Segment(self.count_reader * INT64)
        self.writer_id = Segment(self.count_writer * INT64)
        self.data = Segment(
            self.count_writer * (self.cell_amount * self.data_size)
        )
        self.data_header = Segment(
            self.count_writer * (self.cell_amount * INT64)
        )

    def post_init(self) -> None:
        """Called by managers after binding segments to shared memory.
        Premature invocation will cause runtime or logical errors."""
        if self.cast_to_int64:
            self.data_buf = self.data.view.cast("q")
            self.data_size = self.data_size // 8
        else:
            self.data_buf = self.data.view

        self.data_header_buf = self.data_header.view.cast("q")

        self.wid_buf = self.writer_id.view.cast("q")
        self.rid_buf = self.reader_id.view.cast("q")

    def reset(self) -> None:
        """Resets current read and write cells to 0."""
        for idx in range(self.count_writer):
            self.wid_buf[idx] = 0

        for idx in range(self.count_reader):
            self.rid_buf[idx] = 0

    def lag_not_is_safe(self) -> bool:
        """Checks the distance between the current write cell and current read cells.
        Used as protection against overwriting unread data.
        Also prevents race conditions when a reader accesses a cell's data view before finishing reading the previous cell."""
        for rid in range(self.count_reader):
            if (
                (self.wid_buf[0] - self.rid_buf[rid] + self.cell_amount)
                % self.cell_amount
            ) > self.safe_lag:
                return True

        return False

    def get_cell(self) -> int:
        """Returns the data offset for packing."""
        cell: int = self.wid_buf[0]
        return cell * self.data_size

    def set_cell(self, len_data: int) -> None:
        """Sets the length of written data and advances the write cell.

        Raises
        ------
            if len_data exceeds cell size"""
        if len_data > self.data_size:
            raise ValueError(
                f"Data length ({len_data}) exceeds cell size ({self.data_size})"
            )
        self.data_header_buf[self.wid_buf[0]] = len_data
        new_cell = self.wid_buf[0] + 1
        self.wid_buf[0] = new_cell if new_cell < self.cell_amount else 0

    def set_data(self, raw_data: bytes | memoryview) -> None:
        """Base method for packing data into the buffer.
        If the buffer is cast, iteration is used."""
        start: int = self.get_cell()
        lrd: int = len(raw_data)
        if self.cast_to_int64:
            for idx, data in enumerate(raw_data):
                self.data_buf[start + idx] = data
        else:
            self.data_buf[start : start + lrd] = raw_data

        self.set_cell(len_data=lrd)

    def get_data(self, reader: int = 0) -> memoryview:
        """The sole method for retrieving written data.
        Returns a memory view of data protected by safe_lag.
        Casted buffers support unpacking iteration:
            >>> a, b, c = buf[slice]"""

        cell: int = self.rid_buf[reader]
        lrd: int = self.data_header_buf[cell]
        start: int = cell * self.data_size
        raw_data: memoryview = self.data_buf[start : start + lrd]
        new_cell: int = cell + 1
        self.rid_buf[reader] = new_cell if new_cell < self.cell_amount else 0
        return raw_data


@dataclass(slots=True)
class MemoryLayout(ABC):
    """Abstract base class for all memory layouts. Used for clean and safe creation of unified buffers sliced into segments with convenient access.
    Also serves as a marker for group interactions.
    Upon initialization, it iterates through all class and ring buffer attributes, collects segments, computes their offsets,
    and calculates the total requested size. If alignment is enabled, the final size is rounded up to the nearest 4096-byte page.
    Alignment is optional since the OS already manages page allocations; it is primarily for clarity so developers understand why a 128-byte layout results in a 4096-byte allocation.
    Typically backed by shared memory, though other memory views can be used."""

    size: int = 0
    align: bool = True
    segments: dict[str, Segment] = field(default_factory=dict)
    rings: dict[str, RingBuf] = field(default_factory=dict)

    @final
    def __post_init__(self) -> None:
        self.child_post_init()
        self.__collect_segments_and_rings()
        offset = self.__calculate_offsets()
        self.size = ((offset + 4095) // 4096) * 4096 if self.align else offset

    def child_post_init(self) -> None:
        """Wrapper method so subclasses don't need to override __post_init__ with multiple Parent.__post_init__(self) calls.
        Using super() in dataclass(slots=True) does not work correctly because dataclasses generate a new class."""

    @final
    def reset(self) -> None:
        """Used by the main process before the next system run to reset shared memory to its default state.
        Logically called only during backtesting."""
        for _name, ring in self.rings.items():  # noqa:PERF102
            ring.reset()

        self.child_reset()

    def child_reset(self) -> None: ...

    @final
    def __collect_segments_and_rings(self) -> None:
        """Collects all Segments and RingBufs from the subclass slots, and Segments from RingBuf slots into lists.
        Raises an error if a declared attribute is missing. Inspects top-level attributes only."""
        for attr_name in self.__slots__:
            attr_obj = getattr(self, attr_name)
            if isinstance(attr_obj, Segment):
                self.segments[attr_name] = attr_obj

            elif isinstance(attr_obj, RingBuf):
                self.rings[attr_name] = attr_obj
                for ring_attr_name in attr_obj.__slots__:
                    if hasattr(attr_obj, ring_attr_name):
                        ring_attr_obj = getattr(attr_obj, ring_attr_name)
                        if isinstance(ring_attr_obj, Segment):
                            self.segments[f"{attr_name}_{ring_attr_name}"] = (
                                ring_attr_obj
                            )

    @final
    def __calculate_offsets(self) -> int:
        """Calculates the offset for each Segment accounting for accumulated offsets, and returns the total offset at the end.
        Attribute order is not guaranteed."""
        offset: int = 0
        for seg in self.segments.values():
            seg.offset = (offset, (offset := (offset + seg.size)))

        return offset

    @final
    def bind_memory(self, buf: memoryview) -> None:
        """Binds segments to a memory view using their computed offsets."""
        for _name, seg in self.segments.items():  # noqa:PERF102
            seg.view = buf[slice(*seg.offset)]

    @final
    def post_init_rings(self) -> None:
        """Performs post-initialization logic for ring buffers which typically require memory-bound segments."""
        for _name, ring in self.rings.items():  # noqa:PERF102
            ring.post_init()


@final
@dataclass(slots=True)
class Metrics(MemoryLayout):
    """Container for flags/metrics used for inter-process synchronization.

    Attributes
    ----------
    procs_status : Segment
        Process status flags.
    main_status : Segment
        Process invocation counters. After updating procs_status, a process increments its invocation counter.
        If a process counter is positive, the main process checks the process and decrements the counter.
    trade_read_time : Segment
        Timestamp of the last analyzed trade. Used by the simulator to catch up the footprint engine when reading the trade stream.
    engine_complete : Segment
        Set when all trades in the buffer have been read and analyzed.
    """

    count_procs: int = 10

    procs_status: Segment = field(init=False)
    main_status: Segment = field(init=False)
    trade_read_time: Segment = field(
        default_factory=lambda: Segment(INT64), init=False
    )
    engine_complete: Segment = field(
        default_factory=lambda: Segment(INT64), init=False
    )

    @override
    def child_post_init(self) -> None:
        self.procs_status = Segment((self.count_procs * 2) * INT64)
        self.main_status = Segment(self.count_procs * INT64)

    @override
    def child_reset(self) -> None:
        """Resets inter-process synchronization flags."""
        self.trade_read_time.view.cast("q")[0] = 0
        self.engine_complete.view.cast("q")[0] = 0


@dataclass(slots=True)
class LogStream(MemoryLayout):
    """Ring buffer for transmitting process logs to the main process.
    Provides high-speed logging including process log timestamps for precise debugging.
    If the main process cannot keep up with log processing, worker processes skip new logs
    and notify the main process via status codes (an alternative logging mechanism utilizing static logs, primarily used for IPC coordination).
    Identical across all modes."""

    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=1024, cell_amount=100, count_reader=10, count_writer=10
        ),
        init=False,
    )


@dataclass(slots=True)
class SignalStream(MemoryLayout):
    """Ring buffer for transmitting position open/close signals. Identical across all modes."""

    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(6 * 8), cell_amount=1000, cast_to_int64=True
        ),
        init=False,
    )

    def set_data(
        self,
        signal_id: int,
        nPrice: int,
        timestamp: int,
        order_param: int,
        tp_dev: int,
        sl_dev: int,
    ) -> None:
        start: int = self.ring_buf.get_cell()
        self.ring_buf.data_buf[start] = signal_id
        self.ring_buf.data_buf[start + 1] = nPrice
        self.ring_buf.data_buf[start + 2] = timestamp
        self.ring_buf.data_buf[start + 3] = order_param
        self.ring_buf.data_buf[start + 4] = tp_dev
        self.ring_buf.data_buf[start + 5] = sl_dev
        self.ring_buf.set_cell(len_data=6)


@dataclass(slots=True)
class UserDataStream(MemoryLayout):
    """Ring buffer for transmitting account data (executed orders and changed balances).
    In live mode, a custom packing method is used for structures containing exchange-decoded data from adapters.
    In backtest mode, standard scalar iteration packing is used."""

    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(c.TP_ConstantCount * 8),
            cell_amount=1000,
            cast_to_int64=True,
        ),
        init=False,
    )

    def set_data_in_live(self, data: OrderData | BalanceData) -> None:
        start: int = self.ring_buf.get_cell()
        if isinstance(data, OrderData):
            self.ring_buf.data_buf[start + c.TP_timestamp] = data.timestamp
            self.ring_buf.data_buf[start + c.TP_order_param] = data.order_param
            self.ring_buf.data_buf[start + c.TP_order_id] = data.order_id
            self.ring_buf.data_buf[start + c.TP_client_order_id] = (
                data.client_order_id
            )
            self.ring_buf.data_buf[start + c.TP_nPrice] = data.nPrice
            self.ring_buf.data_buf[start + c.TP_nQty] = data.nQty
            self.ring_buf.data_buf[start + c.TP_nCommission] = data.nCommission
            lrd = 7
        else:
            self.ring_buf.data_buf[start] = data.nBalance
            self.ring_buf.data_buf[start + 1] = data.lockedNbalance
            self.ring_buf.data_buf[start + 2] = data.availableNbalance
            lrd = 3
        self.ring_buf.set_cell(len_data=lrd)


@dataclass(slots=True)
class OrderStream(MemoryLayout):
    """Ring buffer for transmitting orders for execution. Identical across all modes."""

    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(5 * 8), cell_amount=1000, cast_to_int64=True
        ),
        init=False,
    )

    def set_data(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        """Packs order parameters for execution instead of using the standard ring buffer packing method."""
        start: int = self.ring_buf.get_cell()
        self.ring_buf.data_buf[start] = timestamp
        self.ring_buf.data_buf[start + 1] = order_param
        self.ring_buf.data_buf[start + 2] = client_order_id
        self.ring_buf.data_buf[start + 3] = nPrice
        self.ring_buf.data_buf[start + 4] = nQty
        self.ring_buf.set_cell(len_data=5)


@dataclass(slots=True)
class MarketDataStream(MemoryLayout):
    """Ring buffer for transmitting trade data,
    read by the engine and the exchange simulator (during backtesting when order execution is enabled).
    In live mode, raw undecoded bytes are transmitted.
    In backtest mode, data is pre-decoded and converted to integer format.
    Default settings are configured for backtesting with 2 readers."""

    data_size: int = 32
    cell_amount: int = 100_000
    count_reader: int = 2
    cast_to_int64: bool = True

    ring_buf: RingBuf = field(init=False)

    @override
    def child_post_init(self) -> None:
        self.ring_buf = RingBuf(
            data_size=self.data_size,
            cell_amount=self.cell_amount,
            count_reader=self.count_reader,
            cast_to_int64=self.cast_to_int64,
        )

    def set_data_in_backtest(
        self, nPrice: int, nQty: int, timestamp: int, is_sell: int
    ) -> None:
        """Packs pre-prepared trade data into the buffer.
        Used exclusively during backtesting."""
        start: int = self.ring_buf.get_cell()
        self.ring_buf.data_buf[start] = nPrice
        self.ring_buf.data_buf[start + 1] = nQty
        self.ring_buf.data_buf[start + 2] = timestamp
        self.ring_buf.data_buf[start + 3] = is_sell
        self.ring_buf.set_cell(len_data=4)


@dataclass(slots=True)
class MarketDataGapStream(MemoryLayout):
    """Ring buffer for transmitting downloaded aggregated trade packages to the engine
    and handling trade download requests from the engine. Used exclusively in live mode."""

    gap_first_id: Segment = field(
        default_factory=lambda: Segment(INT64), init=False
    )
    gap_last_id: Segment = field(
        default_factory=lambda: Segment(INT64), init=False
    )
    have_gap: Segment = field(
        default_factory=lambda: Segment(INT64), init=False
    )
    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(data_size=256 * 1000, cell_amount=6),
        init=False,
    )
