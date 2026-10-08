"""Shared memory layout and component configuration data structures.

This module provides configuration classes, memory segment representations, and
inter-process communication (IPC) ring buffers used across the trading engine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import final, override

from imprint._core import constant as c
from imprint._core.settings import Timeframe
from imprint._core.utils.base_adapters import BalanceData, OrderData

PERCENT: int = 10_000

OFFSET: int = 0
INT64: int = 8
FLOAT64: int = 8


@final
@dataclass(slots=True)
class Segment:
    """Represents a shared memory segment with a fixed byte size.

    Parameters
    ----------
    size : int
        Size of the memory segment in bytes. Must be non-negative.

    Attributes
    ----------
    size : int
        Size of the memory segment in bytes.
    offset : tuple[int, int]
        Start and end byte offsets within the parent shared memory block.
    view : memoryview
        Memory view buffer providing direct byte-level access.
    """

    size: int

    offset: tuple[int, int] = field(default=None, init=False)  # pyright: ignore[reportAssignmentType]
    view: memoryview = field(default=None, init=False)  # pyright: ignore[reportAssignmentType]


@final
@dataclass(slots=True)
class Percent:
    """Represents a percentage value scaled to an integer basis point representation.

    Parameters
    ----------
    base : float
        Percentage value (e.g., ``5.0`` for 5%).

    Attributes
    ----------
    base : float
        Original percentage input value.
    fixed : int
        Scaled integer representation using `PERCENT` (10,000) as 100%.
    """

    base: float

    fixed: int = field(init=False)

    def __post_init__(self) -> None:
        self.fixed = round(self.base / 100 * PERCENT)


@dataclass
class Configuration(ABC):
    """Abstract base class for engine configuration objects."""


@final
@dataclass(slots=True)
class Setup(Configuration):
    """Configures core engine startup parameters and component modules.

    Attributes
    ----------
    backtesting : bool, default=True
        Enables backtesting execution mode.
    execution : bool, default=True
        Enables live order execution mode.
    backtest_start_date : str, default="2026-01-01"
        Backtest starting date string in ``YYYY-MM-DD`` format.
    backtest_end_date : str, default="2026-01-01"
        Backtest ending date string in ``YYYY-MM-DD`` format.
    algorithm_module : str, default=""
        Python module path containing the trading algorithm.
    algorithm_class_name : str, default=""
        Class name of the trading algorithm.
    execution_module : str, default=""
        Python module path containing the execution adapter.
    execution_class_name : str, default=""
        Class name of the execution adapter.
    agg_trades_decoder_module : str, default=""
        Python module path for aggregate trades decoding.
    agg_trades_decoder_class_name : str, default=""
        Class name of the aggregate trades decoder.
    user_stream_decoder_module : str, default=""
        Python module path for user data stream decoding.
    user_stream_decoder_class_name : str, default=""
        Class name of the user data stream decoder.
    order_encoder_module : str, default=""
        Python module path for order encoding.
    order_encoder_class_name : str, default=""
        Class name of the order encoder.
    exchange_rest_module : str, default=""
        Python module path for exchange REST client.
    exchange_rest_class_name : str, default=""
        Class name of the exchange REST client.
    """

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
    """Configures network connection endpoints for REST and WebSocket streams.

    Attributes
    ----------
    base_rest_url : str, default=""
        Base URL for exchange REST API endpoints.
    market_data_stream_url : str, default=""
        WebSocket URL for real-time market data feed.
    user_data_stream_url : str, default=""
        WebSocket URL for user account data updates.
    order_stream_url : str, default=""
        WebSocket URL for order execution updates.
    """

    base_rest_url: str = ""
    market_data_stream_url: str = ""
    user_data_stream_url: str = ""
    order_stream_url: str = ""


@final
@dataclass(slots=True)
class Account(Configuration):
    """Configures account financial parameters, leverage, and execution limits.

    Attributes
    ----------
    leverage : int, default=20
        Trading leverage multiplier. Must be positive.
    balance : float, default=100.0
        Initial account balance in quote currency.
    min_order_size : float, default=5.0
        Minimum allowable order value in base currency.
    taker_commission : Percent, default=Percent(0.05)
        Taker fee percentage.
    maker_commission : Percent, default=Percent(0.02)
        Maker fee percentage.
    slippage : Percent, default=Percent(0.05)
        Simulated order execution slippage percentage.
    latency_ms : int, default=100
        Simulated network round-trip latency in milliseconds.
    scale_prec : int, default=8
        Decimal precision scaling factor exponent.
    active_order_limit : int, default=1000
        Maximum concurrent active orders allowed.
    scale_mult : int
        Calculated multiplier factor equal to ``10**scale_prec``.
    """

    leverage: int = 20
    balance: float = 100.0
    min_order_size: float = 5.0
    taker_commission: Percent = field(default_factory=lambda: Percent(0.05))
    maker_commission: Percent = field(default_factory=lambda: Percent(0.02))
    slippage: Percent = field(default_factory=lambda: Percent(0.05))
    latency_ms: int = 100
    scale_prec: int = 8
    active_order_limit: int = 1000

    scale_mult: int = field(init=False)

    def __post_init__(self) -> None:
        self.scale_mult = 10**self.scale_prec


@final
@dataclass(slots=True)
class RiskManagement(Configuration):
    """Configures risk thresholds, position sizing, and protective stop/take-profit parameters.

    Attributes
    ----------
    max_lock_balance : Percent, default=Percent(10)
        Maximum allowable locked balance percentage.
    max_loss_balance : Percent, default=Percent(10)
        Maximum allowable cumulative loss percentage before circuit breaker triggers.
    entry_qty : Percent, default=Percent(1)
        Position entry size as a percentage of available balance.
    tp_dev : Percent, default=Percent(5)
        Take-profit deviation percentage.
    sl_dev : Percent, default=Percent(5)
        Stop-loss deviation percentage.
    pass_signal_if_analysis_time_big : int, default=50_000
        Maximum allowed analysis execution time in microseconds before dropping signal.
    pass_execute_signal_if_timer_ms_exepired : int, default=1_000
        Maximum allowed signal execution delay in milliseconds before expiration.
    """

    max_lock_balance: Percent = field(default_factory=lambda: Percent(10))
    max_loss_balance: Percent = field(default_factory=lambda: Percent(10))
    entry_qty: Percent = field(default_factory=lambda: Percent(1))
    tp_dev: Percent = field(default_factory=lambda: Percent(5))
    sl_dev: Percent = field(default_factory=lambda: Percent(5))
    pass_signal_if_analysis_time_big: int = 50_000
    pass_execute_signal_if_timer_ms_exepired: int = 1_000


@final
@dataclass(slots=True)
class Coin(Configuration):
    """Configures trading instrument symbols, precision rules, and tick/lot sizes.

    Attributes
    ----------
    symbol : str, default="DASHUSDT"
        Exchange trading pair identifier.
    tick_size : str, default="0.01"
        Minimum price movement increment string representation.
    lot_size : str, default="0.001"
        Minimum order quantity increment string representation.
    """

    symbol: str = "DASHUSDT"
    tick_size: str = "0.01"
    lot_size: str = "0.001"

    @property
    def price_prec(self) -> int:
        """Number of decimal places for price formatting derived from ``tick_size``."""
        return (
            len(self.tick_size.split(sep=".")[-1])
            if "." in self.tick_size
            else 0
        )

    @property
    def qty_prec(self) -> int:
        """Number of decimal places for quantity formatting derived from ``lot_size``."""
        return (
            len(self.lot_size.split(sep=".")[-1]) if "." in self.lot_size else 0
        )

    @property
    def price_mult(self) -> int:
        """Integer scaling multiplier for price values derived from ``price_prec``."""
        return 10**self.price_prec

    @property
    def qty_mult(self) -> int:
        """Integer scaling multiplier for quantity values derived from ``qty_prec``."""
        return 10**self.qty_prec


@final
@dataclass(slots=True)
class Footprint(Configuration):
    """Configures footprint chart dimensions, aggregation timeframes, and layout state.

    Attributes
    ----------
    timeframe : Timeframe, default=Timeframe.H1
        Candle aggregation timeframe interval.
    chart_range : int, default=1
        Chart time span range in days.
    step_tick : int, default=1
        Price step increment in ticks per footprint row.
    fp_rows : int, default=10001
        Total number of price rows per footprint matrix.
    state : bool, default=False
        Enables persistent footprint state tracking.
    ctrade : bool, default=False
        Enables cumulative trade delta tracking.
    colVP : int
        Volume profile column index offset.
    colDP : int
        Delta profile column index offset.
    bar_count : int
        Total number of chart bars calculated from timeframe and chart range.
    fp_cols : int
        Total number of footprint data columns.
    fp_panel_cols : int
        Total footprint panel columns including header/metadata columns.
    """

    timeframe: Timeframe = Timeframe.H1
    chart_range: int = 1
    step_tick: int = 1
    fp_rows: int = 10001
    state: bool = False
    ctrade: bool = False

    colVP: int = field(default=-2, init=False)
    colDP: int = field(default=-1, init=False)
    bar_count: int = field(init=False)
    fp_cols: int = field(init=False)
    fp_panel_cols: int = field(init=False)

    def __post_init__(self) -> None:
        self.bar_count = self._get_bar_count(day=self.chart_range)
        self.fp_cols = self.bar_count * 2
        self.fp_panel_cols = self.fp_cols + 2

    def _get_bar_count(self, day: int) -> int:
        """Calculate total bar count for a given day range and timeframe.

        Parameters
        ----------
        day : int
            Duration in days. Must be positive.

        Returns
        -------
        int
            Total number of bars fitting within the specified duration.
        """
        dayMs: int = max(day, 1) * 24 * 60 * 60 * 1000
        ivlMs: int = self.timeframe
        return (dayMs // ivlMs) if (dayMs > ivlMs) else (ivlMs // dayMs)


# - - - Configs For IPC - - -
@dataclass(slots=True)
class SharedMemorySegments(ABC):
    """Abstract base class for shared memory segment container configurations.

    Attributes
    ----------
    shm_size : int, default=0
        Total allocated shared memory size in bytes, aligned to page boundaries (4096 bytes).
    """

    shm_size: int = 0

    @final
    def __post_init__(self) -> None:
        self.child_post_init()
        self.shm_size = ((self.__get_need_shm_size() // 4096) + 1) * 4096

    def child_post_init(self) -> None:
        """Perform subclass-specific initialization for shared memory segments."""

    @abstractmethod
    def reset(self) -> None: ...

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
            elif isinstance(attr_obj, RingBuf):
                for ring_attr_name in attr_obj.__slots__:
                    if hasattr(attr_obj, ring_attr_name):
                        ring_attr_obj = getattr(attr_obj, ring_attr_name)
                        if isinstance(ring_attr_obj, Segment):
                            ring_attr_obj.offset = (
                                offset,
                                (offset := (offset + ring_attr_obj.size)),
                            )

        return offset


@final
@dataclass(slots=True)
class Metrics(SharedMemorySegments):
    """Manages shared memory segment layouts for engine performance metrics and process statuses.

    Parameters
    ----------
    count_procs : int, default=10
        Total number of tracked background processes.

    Attributes
    ----------
    count_procs : int
        Total number of tracked background processes.
    procs_status : Segment
        Shared memory segment storing process health status flags.
    main_status : Segment
        Shared memory segment storing main control process status.
    time_start_reading : Segment
        Shared memory segment storing engine read startup timestamp.
    trade_read_time : Segment
        Shared memory segment storing trade message read duration.
    engine_complete : Segment
        Shared memory segment storing engine completion status flag.
    """

    count_procs: int = 10

    procs_status: Segment = field(init=False)
    main_status: Segment = field(init=False)
    time_start_reading: Segment = field(init=False)
    trade_read_time: Segment = field(init=False)
    engine_complete: Segment = field(init=False)

    @override
    def child_post_init(self) -> None:
        self.procs_status = Segment((self.count_procs * 2) * INT64)
        self.main_status = Segment(self.count_procs * INT64)
        self.time_start_reading = Segment(INT64)
        self.trade_read_time = Segment(INT64)
        self.engine_complete = Segment(INT64)

    @override
    def reset(self) -> None:
        self.time_start_reading.view.cast("q")[0] = 0
        self.trade_read_time.view.cast("q")[0] = 0
        self.engine_complete.view.cast("q")[0] = 0


# - - Base Ring Buf For All Streams - -
@final
@dataclass(slots=True)
class RingBuf:
    """Implements a lock-free circular ring buffer over shared memory for inter-process communication.

    Parameters
    ----------
    data_size : int, default=256
        Byte size of each individual data cell.
    cell_amount : int, default=100
        Total number of cells in the ring buffer. Must be positive.
    count_writer : int, default=1
        Number of concurrent writer processes.
    count_reader : int, default=1
        Number of concurrent reader processes.
    cast_to_int64 : bool, default=False
        If True, casts data memory buffer view to 64-bit signed integers.

    Attributes
    ----------
    data_size : int
        Byte size per cell.
    cell_amount : int
        Total capacity in cells.
    count_writer : int
        Number of writers.
    count_reader : int
        Number of readers.
    cast_to_int64 : bool
        Flag indicating 64-bit integer casting.
    data_header_size : int
        Header size in bytes per cell (default 8).
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

    data_header_size: int = field(default=8, init=False)
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
        self.safe_lag = int(self.cell_amount * 0.9)

        self.reader_id = Segment(self.count_reader * INT64)
        self.writer_id = Segment(self.count_writer * INT64)
        self.data = Segment(
            self.count_writer * (self.cell_amount * self.data_size)
        )
        self.data_header = Segment(
            self.count_writer * (self.cell_amount * self.data_header_size)
        )

    def post_init(self) -> None:
        """Initialize memory views and cast buffer types after shared memory attachment."""
        if self.cast_to_int64:
            self.data_buf = self.data.view.cast("q")
            self.data_size = self.data_size // 8
        else:
            self.data_buf = self.data.view

        self.data_header_buf = self.data_header.view.cast("q")

        self.wid_buf = self.writer_id.view.cast("q")
        self.rid_buf = self.reader_id.view.cast("q")

    def reset(self) -> None:
        for idx in range(self.count_writer):
            self.wid_buf[idx] = 0

        for idx in range(self.count_reader):
            self.rid_buf[idx] = 0

    def lag_not_is_safe(self) -> bool:
        """Check whether any reader lags behind the writer beyond the safe threshold.

        Returns
        -------
        bool
            True if any reader lag exceeds ``safe_lag``, otherwise False.
        """
        for rid in range(self.count_reader):
            if (
                (self.wid_buf[0] - self.rid_buf[rid] + self.cell_amount)
                % self.cell_amount
            ) > self.safe_lag:
                return True

        return False

    def get_cell(self) -> int:
        """Retrieve the starting byte offset for the current writer cell.

        Returns
        -------
        int
            Byte offset representing the start of the current write cell.
        """
        cell: int = self.wid_buf[0]
        return cell * self.data_size

    def set_cell(self, len_data: int) -> None:
        """Advance the writer cursor and record the written data length for the current cell.

        Parameters
        ----------
        len_data : int
            Number of bytes or elements written in the current cell. Must be non-negative.
        """
        self.data_header_buf[self.wid_buf[0]] = len_data
        new_cell = self.wid_buf[0] + 1
        self.wid_buf[0] = new_cell if new_cell < self.cell_amount else 0

    def get_data(self) -> memoryview:
        """Read data from the current reader cell and advance the reader cursor.

        Returns
        -------
        memoryview
            Memory view slice containing the read data payload.
        """
        cell: int = self.rid_buf[0]
        lrd: int = self.data_header_buf[cell]
        start: int = cell * self.data_size
        raw_data: memoryview = self.data_buf[start : start + lrd]
        new_cell: int = cell + 1
        self.rid_buf[0] = new_cell if new_cell < self.cell_amount else 0
        return raw_data

    def set_data(self, raw_data: bytes | memoryview) -> None:
        """Write raw bytes or memory view data into the current cell and commit.

        Parameters
        ----------
        raw_data : bytes | memoryview
            Data payload to write into the ring buffer cell.
        """
        start: int = self.get_cell()
        lrd: int = len(raw_data)
        self.data_buf[start : start + lrd] = raw_data
        self.set_cell(len_data=lrd)


# - Log Stream -
@dataclass(slots=True)
class LogStream(SharedMemorySegments):
    """Shared memory stream configuration for application logging.

    Attributes
    ----------
    ring_buf : RingBuf
        Circular ring buffer configured for log messages.
    """

    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=1024, cell_amount=100, count_reader=10, count_writer=10
        ),
        init=False,
    )

    @override
    def reset(self) -> None:
        self.ring_buf.reset()


# - Signal Stream -
@dataclass(slots=True)
class SignalStream(SharedMemorySegments):
    """Shared memory stream configuration for trading signal transmission.

    Attributes
    ----------
    ring_buf : RingBuf
        Circular ring buffer configured for 64-bit integer signal parameters.
    """

    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(6 * 8), cell_amount=1000, cast_to_int64=True
        ),
        init=False,
    )

    @override
    def reset(self) -> None:
        self.ring_buf.reset()

    def set_data(
        self,
        signal_id: int,
        nPrice: int,
        timestamp: int,
        order_param: int,
        tp_dev: int,
        sl_dev: int,
    ) -> None:
        """Write a trading signal data record into the signal ring buffer.

        Parameters
        ----------
        signal_id : int
            Unique identifier of the trading signal.
        nPrice : int
            Scaled integer execution price.
        timestamp : int
            Signal generation UNIX timestamp in milliseconds.
        order_param : int
            Encoded order parameter bitmask or flag.
        tp_dev : int
            Take-profit deviation parameter.
        sl_dev : int
            Stop-loss deviation parameter.
        """
        start: int = self.ring_buf.get_cell()
        self.ring_buf.data_buf[start] = signal_id
        self.ring_buf.data_buf[start + 1] = nPrice
        self.ring_buf.data_buf[start + 2] = timestamp
        self.ring_buf.data_buf[start + 3] = order_param
        self.ring_buf.data_buf[start + 4] = tp_dev
        self.ring_buf.data_buf[start + 5] = sl_dev
        self.ring_buf.set_cell(len_data=6)


# - User Data Stream -
@dataclass(slots=True)
class UserDataStream(SharedMemorySegments):
    """Shared memory stream configuration for user account balances and order updates.

    Attributes
    ----------
    ring_buf : RingBuf
        Circular ring buffer configured for user data records.
    """

    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(c.TP_ConstantCount * 8),
            cell_amount=1000,
            cast_to_int64=True,
        ),
        init=False,
    )

    @override
    def reset(self) -> None:
        self.ring_buf.reset()

    def set_data_in_live(self, data: OrderData | BalanceData) -> None:
        """Write live order or balance update data into the user data ring buffer.

        Parameters
        ----------
        data : OrderData | BalanceData
            Adapter data structure containing either order execution details or account balance information.
        """
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


# - Order Stream -
@dataclass(slots=True)
class OrderStream(SharedMemorySegments):
    """Shared memory stream configuration for outbound order requests.

    Attributes
    ----------
    ring_buf : RingBuf
        Circular ring buffer configured for order request records.
    """

    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(5 * 8), cell_amount=1000, cast_to_int64=True
        ),
        init=False,
    )

    @override
    def reset(self) -> None:
        self.ring_buf.reset()

    def set_data(
        self,
        timestamp: int,
        order_param: int,
        client_order_id: int,
        nPrice: int,
        nQty: int,
    ) -> None:
        """Write an outbound order request record into the order ring buffer.

        Parameters
        ----------
        timestamp : int
            Order request UNIX timestamp in milliseconds.
        order_param : int
            Encoded order parameter flags (e.g., side, type).
        client_order_id : int
            Unique client-assigned order identifier.
        nPrice : int
            Scaled integer order limit price.
        nQty : int
            Scaled integer order quantity.
        """
        start: int = self.ring_buf.get_cell()
        self.ring_buf.data_buf[start] = timestamp
        self.ring_buf.data_buf[start + 1] = order_param
        self.ring_buf.data_buf[start + 2] = client_order_id
        self.ring_buf.data_buf[start + 3] = nPrice
        self.ring_buf.data_buf[start + 4] = nQty
        self.ring_buf.set_cell(len_data=5)


# - Market Data Stream -
@dataclass(slots=True)
class MarketDataStream(SharedMemorySegments):
    """Shared memory stream configuration for real-time market trades and ticker data.

    Parameters
    ----------
    data_size : int, default=256
        Byte size of each market data cell.
    count_reader : int, default=2
        Number of concurrent reader processes.
    cast_to_int64 : bool, default=False
        If True, casts data memory buffer view to 64-bit signed integers.

    Attributes
    ----------
    data_size : int
        Byte size per cell.
    count_reader : int
        Number of readers.
    cast_to_int64 : bool
        Flag indicating 64-bit integer casting.
    ring_buf : RingBuf
        Circular ring buffer configured for market data records.
    """

    data_size: int = 256
    count_reader: int = 2
    cast_to_int64: bool = False

    ring_buf: RingBuf = field(init=False)

    @override
    def reset(self) -> None:
        self.ring_buf.reset()

    @override
    def child_post_init(self) -> None:
        self.ring_buf = RingBuf(
            data_size=self.data_size,
            cell_amount=10_000,
            count_reader=self.count_reader,
            cast_to_int64=self.cast_to_int64,
        )

    def set_data_in_backtest(
        self, nPrice: int, nQty: int, timestamp: int, is_sell: int
    ) -> None:
        """Write a backtest trade tick record into the market data ring buffer.

        Parameters
        ----------
        nPrice : int
            Scaled integer trade execution price.
        nQty : int
            Scaled integer trade execution quantity.
        timestamp : int
            Trade execution UNIX timestamp in milliseconds.
        is_sell : int
            Flag indicating whether trade is a sell (1 for sell, 0 for buy).
        """
        start: int = self.ring_buf.get_cell()
        self.ring_buf.data_buf[start] = nPrice
        self.ring_buf.data_buf[start + 1] = nQty
        self.ring_buf.data_buf[start + 2] = timestamp
        self.ring_buf.data_buf[start + 3] = is_sell
        self.ring_buf.set_cell(len_data=4)


@dataclass(slots=True)
class MarketDataGapStream(SharedMemorySegments):
    """Shared memory stream configuration for tracking market data sequence gaps.

    Attributes
    ----------
    gap_first_id : Segment
        Shared memory segment storing the starting trade ID of a detected gap.
    gap_last_id : Segment
        Shared memory segment storing the ending trade ID of a detected gap.
    have_gap : Segment
        Shared memory segment storing a flag indicating gap presence.
    ring_buf : RingBuf
        Circular ring buffer configured for gap data records.
    """

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

    @override
    def reset(self) -> None:
        self.ring_buf.reset()
