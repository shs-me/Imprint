"""Price, quantity, time, and index coordinate conversion helper."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import final, overload

from numpy import float64, int64

from ... import configs as cfg


@final
@dataclass(slots=True)
class Converter:
    """Converter mapping floating-point values to fixed-point integers and Footprint matrix coordinates."""

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
        self.fp_cols = self.cfgFP.fp_cols
        self.fp_panel_cols = self.cfgFP.fp_panel_cols
        self.bar_count = self.cfgFP.bar_count
        self.idxVP = self.cfgFP.colVP
        self.idxDP = self.cfgFP.colDP

        self.scale = round((float(self.tick_size) * self.step_tick) * self.price_mult)

        if self.total_backtest_days:
            self.total_bar_count = (
                self.total_backtest_days * 24 * 60 * 60 * 1000
            ) // self.tims
        else:
            self.total_bar_count = self.bar_count

    def init_session(self, nPrice: int64, timestamp: int64):
        """Calibrates converter base price, base timestamp, and grid center origin offset."""

        self.baseNprice = (nPrice // self.scale) * self.scale
        self.baseTimestamp = timestamp - (timestamp % self.tims)
        if not self._first_base_timestamp:
            self._first_base_timestamp = self.baseTimestamp

        self.center = self.fp_rows // 2

    def to_idy(self, nPrice: int64) -> int64 | None:
        """Maps fixed-point price to Footprint grid Y-axis row index.

        Returns:
            int64 | None: Grid row index or None if out of bounds.
        """

        idy: int64 = (self.baseNprice - nPrice) // self.scale + self.center
        if 0 <= idy < self.fp_rows:
            return idy
        else:
            return None

    def to_idx(self, timestamp: int64, is_sell: int64) -> int64 | None:
        """Maps timestamp and trade side to Footprint grid X-axis column index.

        Returns:
            int64 | None: Grid column index or None if out of bounds.
        """

        idx: int64 = (timestamp - self.baseTimestamp) // self.tims * 2 + (
            0 if is_sell else 1
        )
        if 0 <= idx < self.fp_cols:
            return idx
        else:
            return None

    @overload
    def to_nPrice(self, value: float64) -> int: ...
    @overload
    def to_nPrice(self, value: float) -> int: ...
    @overload
    def to_nPrice(self, value: int | int64) -> int | int64: ...
    def to_nPrice(self, value: float | float64 | int | int64):
        """Converts float price to fixed-point int or Y-axis row index to fixed-point price."""

        if isinstance(value, (float, float64)):
            return round(value * self.price_mult)
        else:
            return (self.center - value) * self.scale + self.baseNprice

    def to_nQty(self, qty: float) -> int:
        """Converts float quantity to fixed-point int scaling representation."""

        return round(qty * self.qty_mult)

    def to_price(self, nPrice: int | int64) -> float | float64:
        """Converts fixed-point price int to floating-point representation."""

        return nPrice / self.price_mult

    def to_qty(self, nQty: int | int64) -> float | float64:
        """Converts fixed-point quantity int to floating-point representation."""

        return nQty / self.qty_mult

    def to_strftime(self, timestamp_ms: int | int64) -> str:
        """Formats millisecond timestamp as ISO-8601 UTC string."""

        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )

    def get_price(self, idy: int | int64) -> float:
        """Returns rounded float price for specified Footprint row index Y."""

        return round(
            self.to_price(self.to_nPrice(idy)),
            ndigits=self.price_prec,
        )

    @overload
    def get_time(self, idx: int64, strftime: bool = False) -> int64: ...
    @overload
    def get_time(self, idx: int, strftime: bool = True) -> str: ...
    def get_time(self, idx: int | int64, strftime: bool = False):
        """Returns timestamp or formatted string corresponding to bar column index X."""

        if strftime:
            return self.to_strftime((idx & ~1) // 2 * self.tims + self.baseTimestamp)
        else:
            return (idx & ~1) // 2 * self.tims + self.baseTimestamp
