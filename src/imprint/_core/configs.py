"""Shared memory layout and component configuration data structures."""

from abc import ABC
from dataclasses import dataclass, field
from typing import final, override

from imprint._core import constant as c
from imprint._core.settings import Timeframe
from imprint._core.utils.base_adapters import BalanceData, OrderData

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
    base_rest_url: str = ""
    market_data_stream_url: str = ""
    user_data_stream_url: str = ""
    order_stream_url: str = ""


@final
@dataclass(slots=True)
class Account(Configuration):
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
        dayMs: int = max(day, 1) * 24 * 60 * 60 * 1000
        ivlMs: int = self.timeframe
        return (dayMs // ivlMs) if (dayMs > ivlMs) else (ivlMs // dayMs)


# - - - Configs For IPC - - -
@dataclass(slots=True)
class SharedMemorySegments(Configuration, ABC):
    shm_size: int = 0

    @final
    def __post_init__(self) -> None:
        self.child_post_init()
        self.shm_size = ((self.__get_need_shm_size() // 4096) + 1) * 4096

    def child_post_init(self) -> None: ...

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
        self.engine_complete = Segment(UBYTE)


# - - Base Ring Buf For All Streams - -
@final
@dataclass(slots=True)
class RingBuf:
    data_size: int = 256
    data_header_size: int = 1
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
        if self.cast_to_int64:
            self.data_buf = self.data.view.cast("q")
            self.data_size = self.data_size // 8
        else:
            self.data_buf = self.data.view

        if self.data_header_size == 8:
            self.data_header_buf = self.data_header.view.cast("q")
        else:
            self.data_header_buf = self.data_header.view

        self.wid_buf = self.writer_id.view.cast("q")
        self.rid_buf = self.reader_id.view.cast("q")

    def lag_not_is_safe(self) -> bool:
        for rid in range(self.count_reader):
            if (
                (self.wid_buf[0] - self.rid_buf[rid] + self.cell_amount)
                % self.cell_amount
            ) > self.safe_lag:
                return True

        return False

    def get_cell(self) -> int:
        cell: int = self.wid_buf[0]
        return cell * self.data_size

    def set_cell(self, len_data: int) -> None:
        self.data_header_buf[self.wid_buf[0]] = len_data
        new_cell = self.wid_buf[0] + 1
        self.wid_buf[0] = new_cell if new_cell < self.cell_amount else 0

    def get_data(self) -> memoryview:
        cell: int = self.rid_buf[0]
        lrd: int = self.data_header_buf[cell]
        start: int = cell * self.data_size
        raw_data: memoryview = self.data_buf[start : start + lrd]
        new_cell: int = cell + 1
        self.rid_buf[0] = new_cell if new_cell < self.cell_amount else 0
        return raw_data


# - Log Stream -
@dataclass(slots=True)
class LogStream(SharedMemorySegments):
    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=1024,
            data_header_size=8,
            cell_amount=100,
            count_reader=10,
            count_writer=10,
        ),
        init=False,
    )


# - Signal Stream -
@dataclass(slots=True)
class SignalStream(SharedMemorySegments):
    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(6 * 8),
            data_header_size=1,
            cell_amount=1000,
            cast_to_int64=True,
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


# - User Data Stream -
@dataclass(slots=True)
class UserDataStream(SharedMemorySegments):
    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(7 * 8),
            data_header_size=1,
            cell_amount=1000,
            cast_to_int64=True,
        ),
        init=False,
    )

    def set_data(self, data: OrderData | BalanceData) -> None:
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
    ring_buf: RingBuf = field(
        default_factory=lambda: RingBuf(
            data_size=(5 * 8),
            data_header_size=1,
            cell_amount=1000,
            cast_to_int64=True,
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
    data_size: int = 256
    count_reader: int = 2
    cast_to_int64: bool = False

    ring_buf: RingBuf = field(init=False)

    @override
    def child_post_init(self) -> None:
        self.ring_buf = RingBuf(
            data_size=self.data_size,
            data_header_size=1,
            cell_amount=10_000,
            count_reader=self.count_reader,
            cast_to_int64=self.cast_to_int64,
        )

    def set_data_in_live(self, raw_data: bytes | memoryview) -> None:
        start: int = self.ring_buf.get_cell()
        lrd: int = len(raw_data)
        self.ring_buf.data_buf[start : start + lrd] = raw_data
        self.ring_buf.set_cell(len_data=lrd)

    def set_data_in_backtest(
        self, nPrice: int, nQty: int, timestamp: int, is_sell: int
    ) -> None:
        start: int = self.ring_buf.get_cell()
        self.ring_buf.data_buf[start] = nPrice
        self.ring_buf.data_buf[start + 1] = nQty
        self.ring_buf.data_buf[start + 2] = timestamp
        self.ring_buf.data_buf[start + 3] = is_sell
        self.ring_buf.set_cell(len_data=4)
