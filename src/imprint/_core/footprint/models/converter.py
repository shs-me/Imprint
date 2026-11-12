"""Price, quantity, time, and index coordinate conversion helper."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import final

from numba import njit
from numpy import float64, int64

import imprint._core.configs as cfg


@final
@dataclass(slots=True)
class Converter:
    price_prec: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    price_mult: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    qty_prec: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    qty_mult: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    bar_type: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    bar_close_trigger: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    bar_count: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    bar_height: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    profile_height: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    step_tick: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    scale: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    center: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    with_ctrade: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    with_state: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    def post_init(self, cfgCoin: cfg.Coin, cfgFP: cfg.Footprint) -> None:
        self.price_prec[0] = cfgCoin.price_prec
        self.price_mult[0] = cfgCoin.price_mult
        self.qty_prec[0] = cfgCoin.qty_prec
        self.qty_mult[0] = cfgCoin.qty_mult

        self.bar_type[0] = cfgFP.bar_type.bar_type
        self.bar_close_trigger[0] = cfgFP.bar_type.bar_close_trigger
        self.bar_count[0] = cfgFP.bar_count
        self.bar_height[0] = cfgFP.bar_height
        self.profile_height[0] = cfgFP.profile_height
        self.step_tick[0] = cfgFP.step_tick
        self.with_ctrade[0] = cfgFP.ctrade
        self.with_state[0] = cfgFP.state

        self.center[0] = self.bar_height[0] // 2
        self.scale[0] = round(
            (float(cfgCoin.tick_size) * self.step_tick[0]) * self.price_mult[0]
        )

    def to_idy(self, nPrice: int64, baseNprice: int64) -> int64 | None:
        """Map fixed-point price to Footprint grid Y-axis row index.

        Returns
        -------
        int64 | None
            Grid row index ``idy``, or ``None`` if ``nPrice`` falls outside grid bounds.
        """
        idy: int64 = to_idy(
            nPrice,
            baseNprice,
            self.bar_height,
            self.scale,
            self.center,
        )
        return idy if (idy >= 0) else None

    def to_nPrice(self, idy: int | int64, baseNprice: int64) -> int | int64:
        return (self.center[0] - idy) * self.scale[0] + baseNprice

    def to_nQty(self, qty: float) -> int:
        return round(qty * self.qty_mult[0])

    def to_price(self, nPrice: int | int64) -> float | float64:
        return nPrice / self.price_mult[0]

    def to_qty(self, nQty: int | int64) -> float | float64:
        return nQty / self.qty_mult[0]

    def to_strftime(self, timestamp_ms: int | int64) -> str:
        """Format millisecond UTC timestamp as ISO-8601 date string.

        Returns
        -------
        str
            Formatted UTC date string in ``YYYY-MM-DD`` format.
        """
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime(
            "%Y-%m-%d"
        )


@njit(cache=True)
def to_idy(
    nPrice: int64,
    baseNprice: int64,
    bar_height: memoryview,
    scale: memoryview,
    center: memoryview,
) -> int64:
    """Map fixed-point price to Footprint grid Y-axis row index.

    Returns
    -------
    int64
        Grid row index ``idy`` satisfying ``0 <= idy < bar_height``, or ``-1`` if out of bounds.
    """
    idy: int64 = (baseNprice - nPrice) // scale[0] + center[0]
    if 0 <= idy < bar_height[0]:
        return idy
    else:
        return int64(-1)
