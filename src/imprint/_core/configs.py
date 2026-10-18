from __future__ import annotations

from decimal import Decimal
from typing import Any, final, override

import msgspec
from msgspec import field

from imprint._core.settings import Timeframe

PERCENT: int = 10_000


class ValidatedStructMeta(msgspec.StructMeta):
    """Metaclass for `ValidatedStruct`.

    Automatically re-converts any instantiated struct using `msgspec.convert`
    on its dictionary representation, ensuring validation hooks or conversions
    defined by `msgspec` are executed upon initialization.
    """

    @override
    def __call__(cls, *args: Any, **kwargs: Any):
        instance = super().__call__(*args, **kwargs)
        return msgspec.convert(msgspec.structs.asdict(instance), type=cls)


class ValidatedStruct(msgspec.Struct, metaclass=ValidatedStructMeta):
    """Base class for all validated `msgspec.Struct` models in Imprint."""


@final
class Percent(ValidatedStruct):
    """Stores a specified percentage in fractional form along with its integer counterpart. Multiplier: 10,000."""

    base: float
    fixed: int = 0

    def __post_init__(self) -> None:
        self.fixed = round(self.base / 100 * PERCENT)


# -- Base Configs --


class Configuration(ValidatedStruct):
    """Abstract base class for all configurations. Used as a marker for group interactions."""


@final
class Setup(Configuration):
    """Engine parameter settings and module/class names for user adapters.
    Although passing class types directly as parameters works, IPC uses dynamic lazy loading
    based on the adapter module name and class name to prevent circular imports and serialization errors."""

    is_backtesting: bool = True
    with_execution: bool = True
    pass_debug_logs: bool = False
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
class Connector(Configuration):
    """URL endpoint settings for live mode."""

    base_rest_url: str = ""
    market_data_stream_url: str = ""
    user_data_stream_url: str = ""
    order_stream_url: str = ""


@final
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


@final
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

    colVP: int = -2
    colDP: int = -1
    fp_rows: int = 10001

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


# -- Configs Batch Mode --


@final
class AccountBatch(ValidatedStruct):
    leverage: list[int] = field(default_factory=lambda: [20])
    balance: list[float] = field(default_factory=lambda: [100.0])
    min_order_size: list[float] = field(default_factory=lambda: [5.0])
    taker_commission: list[Percent] = field(
        default_factory=lambda: [Percent(0.05)]
    )
    maker_commission: list[Percent] = field(
        default_factory=lambda: [Percent(0.02)]
    )
    slippage: list[Percent] = field(default_factory=lambda: [Percent(0.05)])
    latency_ms: list[int] = field(default_factory=lambda: [100])
    scale_prec: list[int] = field(default_factory=lambda: [8])
    active_order_limit: list[int] = field(default_factory=lambda: [1000])


@final
class FootprintBatch(ValidatedStruct):
    timeframe: list[Timeframe] = field(default_factory=lambda: [Timeframe.H1])
    chart_range: list[int] = field(default_factory=lambda: [1])
    step_tick: list[int] = field(default_factory=lambda: [1])
    state: list[bool] = field(default_factory=lambda: [False])
    ctrade: list[bool] = field(default_factory=lambda: [False])


@final
class RiskManagementBatch(ValidatedStruct):
    max_lock_balance: list[Percent] = field(
        default_factory=lambda: [Percent(10.0)]
    )
    max_loss_balance: list[Percent] = field(
        default_factory=lambda: [Percent(10.0)]
    )
    entry_qty: list[Percent] = field(default_factory=lambda: [Percent(1.0)])
    tp_dev: list[Percent] = field(default_factory=lambda: [Percent(5.0)])
    sl_dev: list[Percent] = field(default_factory=lambda: [Percent(5.0)])
    pass_signal_time: list[int] = field(default_factory=lambda: [50_000])
    expiration_signal_time: list[int] = field(default_factory=lambda: [1000])
