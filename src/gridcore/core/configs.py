"""Shared memory layout and component configuration data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .settings import BarHeaders, SpaceCoords, Timeframe

OFFSET = 0
UBYTE = 1
INT64 = 8
FLOAT64 = 8


class INT(int):
    """Integer subclass marking fields designated for shared memory offset allocation."""

    pass


class Configuration(ABC):
    """Abstract base class for engine configuration objects."""

    def percent_to_int(self) -> None:
        """Converts percentage string fields (e.g., '10%') into basis points integers relative to 10,000."""
        self.percent: int = 10_000
        for name, value in self.__dict__.items():
            if isinstance(value, str):
                setattr(
                    self, name, round(float(value.split("%")[0]) / 100 * self.percent)
                )


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
    agg_trades_struct_module: str = ""
    agg_trades_struct_class_name: str = ""


@dataclass
class Connector(Configuration):
    market_data_uri_for_wss: str = ""
    get_user_data_uri_for_wss: str = ""
    set_user_data_uri_for_wss: str = ""


@dataclass
class Account(Configuration):
    """Account balance, leverage, and commission configurations.

    Attributes:
        leverage (int): Account leverage multiplier.
        balance (float): Initial account equity in quote currency.
        min_order_size (float): Minimum order size in quote currency.
        taker_commission (Any): Taker fee percentage or raw value.
        maker_commission (Any): Maker fee percentage or raw value.
        slippage (Any): Expected slippage deviation percentage.
        latency_ms (Any): Simulated execution latency in milliseconds.
        scale_prec (int): Fixed-point scaling precision exponent.
        save_orders_history (bool): Flag to persist order execution logs to disk.
    """

    leverage: int = 20
    balance: float = 100.0
    min_order_size: float = 5.0
    taker_commission: Any = "0.05%"
    maker_commission: Any = "0.02%"
    slippage: Any = "0.05%"
    latency_ms: Any = 100
    scale_prec: Any = 15
    active_order_limit: int = 1000
    save_orders_history: bool = False

    def __post_init__(self) -> None:
        """Applies basis point conversions and calculates scale precision multiplier."""

        self.percent_to_int()
        self.scale_mult = 10**self.scale_prec


@dataclass
class RiskManagment(Configuration):
    """Strategy risk management and execution parameters.

    Attributes:
        max_lock_balance (Any): Maximum balance allowed for active margin lock.
        max_loss_balance (Any): Maximum tolerable account loss limit.
        entry_qty (Any): Position entry size proportion of available balance.
        tp_dev (Any): Take-profit price deviation percentage.
        sl_dev (Any): Stop-loss price deviation percentage.
        pass_signal_if_analysis_time_big (int): Safe analysis processing latency threshold in microseconds.
        pass_execute_signal_if_timer_ms_exepired (int): Signal execution expiry threshold in milliseconds.
    """

    max_lock_balance: Any = "10%"
    max_loss_balance: Any = "10%"
    entry_qty: Any = "1%"
    tp_dev: Any = "5%"
    sl_dev: Any = "5%"
    pass_signal_if_analysis_time_big: int = 50_000
    pass_execute_signal_if_timer_ms_exepired: int = 1_000

    def __post_init__(self):
        """Applies percentage basis point conversions for strategy attributes."""
        self.percent_to_int()


@dataclass
class Coin(Configuration):
    """Symbol specifications and fixed-point precision settings.

    Attributes:
        symbol (str): Trading pair ticker symbol.
        tick_size (str): Minimum price tick increment.
        lot_size (str): Minimum quantity lot increment.
    """

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
class SharedMemorySegments(Configuration, ABC):
    """Abstract base class for shared memory offset calculation and segment management."""

    shm_size: int = 0

    def __post_init__(self) -> None:
        """Triggers shared memory attribute initialization and page-aligned size calculation."""

        self._set_attr_use_shm()
        self.shm_size = ((self._get_need_shm_size() // 4096) + 1) * 4096

    @abstractmethod
    def _set_attr_use_shm(self) -> None:
        """Abstract method to specify attributes occupying shared memory space."""

        pass

    def _get_need_shm_size(self) -> int:
        """Calculates cumulative byte offsets for fields typed with INT.

        Returns:
            int: Total required byte size for shared memory allocation.
        """

        offset = 0
        for attr_name, attr_obj in self.__dict__.items():
            if isinstance(attr_obj, INT):
                new_value = (offset, (offset := (offset + attr_obj)))
                setattr(self, attr_name, new_value)

        return offset


@dataclass
class Footprint(SharedMemorySegments):
    """Shared memory configuration layout for Footprint matrix and header buffers.

    Attributes:
        timeframe (Timeframe): Bar aggregation timeframe interval.
        chart_range (int): Historical window size in days.
        fp_rows (int): Price row capacity in Footprint grid.
        save_fp_headers (bool): Flag to persist Footprint headers.
        save_algorithm_metadata (bool): Flag to persist strategy analytics.
    """

    timeframe: Timeframe = Timeframe._H
    chart_range: int = 1
    fp_rows: int = 10001
    save_fp_headers: bool = False
    save_algorithm_metadata: bool = False

    def _init_data(self) -> None:
        """Calculates total bar count and column dimensions for Footprint layout."""

        self.colVP, self.colDP = -2, -1
        self.bar_count: int = self._get_bar_count(day=self.chart_range)
        self.fp_cols: int = self.bar_count * 2
        self.fp_panel_cols: int = self.fp_cols + 2

    def _get_bar_count(self, day: int) -> int:
        """Computes total expected bars for the specified chart day range and timeframe.

        Args:
            day (int): Chart scope range in days.

        Returns:
            int: Calculated bar capacity.
        """

        dayMs, ivlMs = (
            (day if day >= 1 else 1) * 24 * 60 * 60 * 1000,
            self.timeframe,
        )
        return (dayMs // ivlMs) if (dayMs > ivlMs) else (ivlMs // dayMs)

    def _set_attr_use_shm(self) -> None:
        """Defines shared memory offset allocations for Footprint arrays, headers, and flags."""

        self._init_data()

        self.footprint: Any = INT(self.fp_rows * self.fp_panel_cols * INT64)
        self.headers: Any = INT(self.bar_count * BarHeaders._ConstantCount * INT64)
        self.metadata: Any = INT(6 * FLOAT64)
        self.space: Any = INT(SpaceCoords._ConstantCount * 2 * INT64)
        self.base_price: Any = INT(INT64)
        self.base_timestamp: Any = INT(INT64)
        self.space_flag: Any = INT(UBYTE)
        self.spare_flag: Any = INT(UBYTE)


@dataclass
class Metrics(SharedMemorySegments):
    """Shared memory layout for inter-process synchronization metrics and status flags."""

    count_procs: int = 10
    text_size: int = 1024

    def _set_attr_use_shm(self) -> None:
        """Allocates shared memory offsets for process status codes, timestamps, and text buffers."""

        self.main: Any = INT(INT64)
        self.status: Any = INT((self.count_procs * 2) * INT64)
        self.text: Any = INT(self.count_procs * self.text_size)
        self.time_start_reading: Any = INT(INT64)
        self.trade_readed_time: Any = INT(INT64)
        self.parsing_complete: Any = INT(UBYTE)
        self.logic_complete: Any = INT(UBYTE)


@dataclass
class BaseRingBuf(ABC):
    """Base template for shared memory ring buffer memory layouts."""

    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 10_000

    def _set_attr_use_shm(self) -> None:
        """Allocates shared memory offsets for reader/writer head positions and data cell arrays."""

        self.reader_id: Any = INT(INT64)
        self.writer_id: Any = INT(INT64)
        self.data: Any = INT(self.cell_amount * self.data_size)
        self.data_header: Any = INT(self.cell_amount * self.data_header_size)


@dataclass
class Signal(BaseRingBuf, SharedMemorySegments):
    """Shared memory ring buffer layout for strategy trade signals."""

    data_size: int = 24
    data_header_size: int = 1
    cell_amount: int = 10_000


@dataclass
class GetUserStream(BaseRingBuf, SharedMemorySegments):
    """Shared memory ring buffer layout for user execution events."""

    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 10_000

    def __post_init__(self) -> None:
        """Initializes ring buffer parent structures and sets safe ring buffer capacity lag threshold."""
        super().__post_init__()
        self.safe_lag: int = int(self.cell_amount * 0.9)


@dataclass
class SetUserStream(BaseRingBuf, SharedMemorySegments):
    """Shared memory ring buffer layout for user execution events."""

    data_size: int = 1024
    data_header_size: int = 8
    cell_amount: int = 10_000

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
