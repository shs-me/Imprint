"""Price, quantity, time, and index coordinate conversion helper."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import final, overload

from numba import njit
from numpy import float64, int64

from imprint._core import configs as cfg


@final
@dataclass(slots=True)
class Converter:
    """
    Convert price, quantity, timestamp, and grid coordinates between raw numerical
    values and Footprint matrix indices.

    Parameters
    ----------
    cfgCoin : cfg.Coin
        Symbol parameters including tick size, lot size, and scale multipliers.
    cfgFP : cfg.Footprint
        Footprint chart configuration settings.
    total_backtest_days : int, default=0
        Total duration of backtesting in days. If zero, default bar count is used.

    Attributes
    ----------
    total_bar_count : int
        Calculated total number of bars across the backtest period or chart range.
    tick_size : str
        Minimum price change increment for the symbol.
    price_prec : int
        Decimal precision of market prices.
    price_mult : int
        Multiplier used to convert prices to fixed-point integers.
    qty_prec : int
        Decimal precision of market quantities.
    qty_mult : int
        Multiplier used to convert quantities to fixed-point integers.
    timeframe : str
        Human-readable timeframe name (e.g. 'H1').
    chart_range : int
        Number of days mapped in the chart range.
    tims : int
        Timeframe duration in milliseconds.
    step_tick : int
        Number of ticks aggregated per footprint row.
    fp_rows : int64
        Total number of row indices along the Y-axis.
    fp_cols : int
        Total number of column indices along the X-axis.
    idxVP : int
        Column index reserved for Volume Profile aggregation.
    idxDP : int
        Column index reserved for Delta Profile aggregation.
    fp_panel_cols : int
        Total columns in the footprint panel including VP and DP side panels.
    bar_count : int
        Number of bars represented in a single chart cycle.
    scale : int
        Price step scaled by price multiplier (`tick_size * step_tick * price_mult`).
    center : int64
        Row index of the Y-axis origin (center row).
    baseNprice : int64
        Scaled base price corresponding to the initial session baseline.
    baseTimestamp : int64
        Base timestamp for the first bar in the current active session.
    """

    cfgCoin: cfg.Coin
    cfgFP: cfg.Footprint
    total_backtest_days: int = 0
    total_bar_count: int = field(init=False)

    tick_size: str = field(init=False)
    price_prec: int = field(init=False)
    price_mult: int = field(init=False)
    qty_prec: int = field(init=False)
    qty_mult: int = field(init=False)
    timeframe: str = field(init=False)
    chart_range: int = field(init=False)
    tims: int = field(init=False)
    step_tick: int = field(init=False)
    fp_rows: int64 = field(init=False)
    fp_cols: int = field(init=False)
    idxVP: int = field(init=False)
    idxDP: int = field(init=False)
    fp_panel_cols: int = field(init=False)
    bar_count: int = field(init=False)
    scale: int = field(init=False)
    center: int64 = field(init=False)
    baseNprice: int64 = field(init=False)
    baseTimestamp: int64 = field(init=False)

    _first_base_timestamp: int64 = field(default=int64(0), init=False)

    def __post_init__(self) -> None:
        self.tick_size = self.cfgCoin.tick_size
        self.price_prec = self.cfgCoin.price_prec
        self.price_mult = self.cfgCoin.price_mult
        self.qty_prec = self.cfgCoin.qty_prec
        self.qty_mult = self.cfgCoin.qty_mult

        self.timeframe = self.cfgFP.timeframe.name
        self.tims = self.cfgFP.timeframe
        self.chart_range = self.cfgFP.chart_range
        self.step_tick = self.cfgFP.step_tick
        self.fp_rows = int64(self.cfgFP.fp_rows)
        self.fp_cols = self.cfgFP.fp_cols
        self.fp_panel_cols = self.cfgFP.fp_panel_cols
        self.bar_count = self.cfgFP.bar_count
        self.idxVP = self.cfgFP.colVP
        self.idxDP = self.cfgFP.colDP

        self.scale = round(
            (float(self.tick_size) * self.step_tick) * self.price_mult
        )

        if self.total_backtest_days:
            self.total_bar_count = (
                self.total_backtest_days * 24 * 60 * 60 * 1000
            ) // self.tims
        else:
            self.total_bar_count = self.bar_count

    def init_session(self, nPrice: int64, timestamp: int64) -> None:
        """
        Calibrate converter base price, base timestamp, and grid center origin offset.

        Parameters
        ----------
        nPrice : int64
            Initial fixed-point price used to establish baseline grid level.
        timestamp : int64
            Initial trade timestamp in milliseconds.
        """

        self.baseNprice = (nPrice // self.scale) * self.scale
        self.baseTimestamp = timestamp - (timestamp % self.tims)
        if not self._first_base_timestamp:
            self._first_base_timestamp = self.baseTimestamp

        self.center = self.fp_rows // 2

    def to_idy(self, nPrice: int64) -> int64 | None:
        """
        Map fixed-point price to Footprint grid Y-axis row index.

        Parameters
        ----------
        nPrice : int64
            Fixed-point price integer.

        Returns
        -------
        int64 or None
            Grid row index `idy`, or `None` if `nPrice` falls outside grid bounds.
        """

        idy: int64 = to_idy(
            nPrice, self.baseNprice, self.scale, self.center, self.fp_rows
        )
        return idy if (idy >= 0) else None

    def to_idx(self, timestamp: int64, is_sell: int64) -> int64 | None:
        """
        Map trade timestamp and side flag to Footprint grid X-axis column index.

        Parameters
        ----------
        timestamp : int64
            Trade execution timestamp in milliseconds.
        is_sell : int64
            Trade side flag (1 for sell/bid, 0 for buy/ask).

        Returns
        -------
        int64 or None
            Grid column index `idx`, or `None` if timestamp falls outside grid bounds.
        """

        idx: int64 = to_idx(
            timestamp, is_sell, self.baseTimestamp, self.tims, self.fp_cols
        )
        return idx if (idx >= 0) else None

    def to_nPrice(self, value: int | int64) -> int64:
        """
        Convert grid Y-axis row index to fixed-point price integer.

        Parameters
        ----------
        value : int or int64
            Footprint grid row index `idy`.

        Returns
        -------
        int64
            Corresponding fixed-point price integer.
        """

        return (self.center - value) * self.scale + self.baseNprice

    def to_nQty(self, qty: float) -> int:
        """
        Convert floating-point quantity to scaled fixed-point integer.

        Parameters
        ----------
        qty : float
            Floating-point trade quantity.

        Returns
        -------
        int
            Scaled integer representation of quantity.
        """

        return round(qty * self.qty_mult)

    def to_price(self, nPrice: int | int64) -> float | float64:
        """
        Convert fixed-point price integer to floating-point representation.

        Parameters
        ----------
        nPrice : int or int64
            Fixed-point price integer.

        Returns
        -------
        float or float64
            Floating-point market price.
        """

        return nPrice / self.price_mult

    def to_qty(self, nQty: int | int64) -> float | float64:
        """
        Convert scaled fixed-point quantity integer to floating-point representation.

        Parameters
        ----------
        nQty : int or int64
            Scaled fixed-point quantity integer.

        Returns
        -------
        float or float64
            Floating-point trade quantity.
        """

        return nQty / self.qty_mult

    def to_strftime(self, timestamp_ms: int | int64) -> str:
        """
        Format millisecond UTC timestamp as ISO-8601 date string.

        Parameters
        ----------
        timestamp_ms : int or int64
            Timestamp in milliseconds.

        Returns
        -------
        str
            Formatted UTC date string (`YYYY-MM-DD`).
        """

        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime(
            "%Y-%m-%d"
        )

    def get_price(self, idy: int | int64) -> float:
        """
        Retrieve rounded floating-point price for given row index Y.

        Parameters
        ----------
        idy : int or int64
            Footprint grid row index.

        Returns
        -------
        float
            Rounded market price matching symbol precision.
        """

        return round(self.to_price(self.to_nPrice(idy)), self.price_prec)

    @overload
    def get_time(self, idx: int64, strftime: bool = False) -> int64: ...
    @overload
    def get_time(self, idx: int, strftime: bool = True) -> str: ...
    def get_time(self, idx: int | int64, strftime: bool = False):
        """
        Retrieve timestamp or formatted date string corresponding to bar column index X.

        Parameters
        ----------
        idx : int or int64
            Footprint grid column index.
        strftime : bool, default=False
            If True, returns ISO date string; otherwise returns timestamp in ms.

        Returns
        -------
        int64 or str
            Millisecond timestamp integer or ISO date string (`YYYY-MM-DD`).
        """

        timestamp: int64 = (idx & ~1) // 2 * self.tims + self.baseTimestamp
        return self.to_strftime(timestamp) if strftime else timestamp


@njit(cache=True)
def to_idy(
    nPrice: int64, baseNprice: int64, scale: int, center: int64, fp_rows: int64
) -> int64:
    """
    Map fixed-point price to Footprint grid Y-axis row index.

    Parameters
    ----------
    nPrice : int64
        Target fixed-point price integer.
    baseNprice : int64
        Session base price integer at grid center.
    scale : int
        Scaled price tick step per row.
    center : int64
        Row index corresponding to origin center offset.
    fp_rows : int64
        Total number of rows in the footprint matrix.

    Returns
    -------
    int64
        Grid row index `idy` (0 <= idy < fp_rows), or -1 if out of bounds.
    """

    idy: int64 = (baseNprice - nPrice) // scale + center
    if 0 <= idy < fp_rows:
        return idy
    else:
        return int64(-1)


@njit(cache=True)
def to_idx(
    timestamp: int64,
    is_sell: int64,
    baseTimestamp: int64,
    tims: int,
    fp_cols: int,
) -> int64:
    """
    Map trade timestamp and order side to Footprint grid X-axis column index.

    Parameters
    ----------
    timestamp : int64
        Trade timestamp in milliseconds.
    is_sell : int64
        Trade side flag (1 for sell/bid side, 0 for buy/ask side).
    baseTimestamp : int64
        Session base timestamp in milliseconds.
    tims : int
        Timeframe duration in milliseconds.
    fp_cols : int
        Total number of trade columns in the footprint matrix.

    Returns
    -------
    int64
        Grid column index `idx` (0 <= idx < fp_cols), or -1 if out of bounds.
    """

    idx: int64 = (timestamp - baseTimestamp) // tims * 2 + (0 if is_sell else 1)
    if 0 <= idx < fp_cols:
        return idx
    else:
        return int64(-1)
