"""Price, quantity, time, and index coordinate conversion helper."""

from datetime import datetime, timezone
from typing import overload

from numpy import float64, int64
from numpy.typing import NDArray

from .... import configs as cfg


class FPconverter:
    """Converter mapping floating-point values to fixed-point integers and Footprint matrix coordinates."""

    def __init__(
        self,
        footprint: NDArray[int64],
        headers: NDArray[int64],
        price_prec: int,
        qty_prec: int,
        cfgFP: cfg.Footprint,
    ) -> None:
        self.footprint: NDArray[int64] = footprint
        self.headers: NDArray[int64] = headers
        self.price_prec: int = price_prec
        self.qty_prec: int = qty_prec

        self.fp_rows: int = cfgFP.fp_rows
        self.fp_cols: int = cfgFP.fp_cols
        self.idxVP: int = cfgFP.colVP
        self.idxDP: int = cfgFP.colDP
        self.fp_panel_cols: int = cfgFP.fp_panel_cols
        self.bar_count: int = cfgFP.bar_count
        self.tims: int = cfgFP.timeframe

        self.price_mult: int = 10**self.price_prec
        self.qty_mult: int = 10**self.qty_prec

    def init_session(self, price: float | int, timestamp: int):
        """Calibrates converter base price, base timestamp, and grid center origin offset."""

        self.nBasePrice: int = (
            self.to_nPrice(price) if isinstance(price, float) else price
        )
        self.baseTimestamp: int = timestamp - (timestamp % self.tims)
        self.center: int = self.fp_rows // 2

    @overload
    def to_idy(self, nPrice: int) -> int | None: ...
    @overload
    def to_idy(self, nPrice: int64) -> int64: ...
    def to_idy(self, nPrice):
        """Maps fixed-point price to Footprint grid Y-axis row index.

        Returns:
            int | int64 | None: Grid row index or None if out of bounds.
        """

        idy: int | int64 = (self.nBasePrice - nPrice) + self.center
        if 0 <= idy < self.fp_rows:
            return idy
        else:
            return None

    def to_idx(self, timestamp: int, is_sell: bool) -> int | None:
        """Maps timestamp and trade side to Footprint grid X-axis column index.

        Returns:
            int | None: Grid column index or None if out of bounds.
        """

        idx: int = (timestamp - self.baseTimestamp) // self.tims * 2 + (
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
    def to_nPrice(self, value):
        """Converts float price to fixed-point int or Y-axis row index to fixed-point price."""

        if isinstance(value, (float, float64)):
            return round(value * self.price_mult)
        else:
            return (self.center - value) + self.nBasePrice

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
            "%Y-%m-%dT%H-%M-%S"
        )

    def get_price(self, idy: int | int64) -> float:
        """Returns rounded float price for specified Footprint row index Y."""

        return round(
            self.to_price(self.to_nPrice(idy)),
            ndigits=self.price_prec,
        )

    def get_qty(self, idy: int, idx: int) -> float:
        """Returns float quantity stored in Footprint cell at coordinates (idy, idx)."""

        return self.to_qty(self.footprint[idy, idx])

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


class ConverterLike:
    def __init__(self, fp_converter: FPconverter, is_bar: bool) -> None:
        self._con: FPconverter = fp_converter
        self._is_bar: bool = is_bar

        self._baseNprice: int64 = int64(0)
        self._nPrice: int64 = self._baseNprice

        self._baseNqty: int | int64 = 0
        self._nQty: int | int64 = self._baseNqty

        self._baseIdy: int64 = int64(0)
        self._idy: int64 = self._baseIdy

        self._baseIdxBid: int | int64 = 0
        self._idxBid: int | int64 = self._baseIdxBid

    @property
    def nPrice(self) -> int64:
        if self._nPrice:
            value = self._nPrice
            self._nPrice = self._baseNprice
        else:
            value = int64(self._con.to_nPrice(self._idy))

        return value

    @property
    def nQty(self) -> int | int64:
        if self._nQty:
            value = self._nQty
        else:
            idy = self._idy if self._idy else self._con.to_idy(self._nPrice)
            idx = (
                slice(self._idxBid, self._idxBid + 2) if self._is_bar else self._idxBid
            )
            value = sum(self._con.footprint[idy, idx])

        self._reset()
        return value

    @property
    def idY(self) -> int64:
        value = self._idy if self._idy else self._con.to_idy(self._nPrice)
        self._reset()
        return value

    def _reset(self) -> None:
        self._nPrice = self._baseNprice
        self._nQty = self._baseNqty
        self._idy = self._baseIdy
        self._idxBid = self._baseIdxBid
