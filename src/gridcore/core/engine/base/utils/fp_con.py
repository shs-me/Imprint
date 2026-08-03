"""Price, quantity, time, and index coordinate conversion helper."""

from datetime import datetime, timezone
from typing import overload

from numpy import float64, int64
from numpy.typing import NDArray

from .... import configs as cfg
from .... import constant as c


class FPconverter:
    """Converter mapping floating-point values to fixed-point integers and Footprint matrix coordinates."""

    def __init__(
        self,
        cfgFP: cfg.Footprint,
        footprint: NDArray[int64],
        headers: NDArray[int64],
        price_prec: int,
        qty_prec: int,
    ) -> None:
        self.fp_rows: int = cfgFP.fp_rows
        self.fp_cols: int = cfgFP.fp_cols
        self.idxVP: int = cfgFP.colVP
        self.idxDP: int = cfgFP.colDP
        self.fp_panel_cols: int = cfgFP.fp_panel_cols
        self.bar_count: int = cfgFP.bar_count
        self.tims: int = cfgFP.timeframe
        self.footprint: NDArray[int64] = footprint
        self.headers: NDArray[int64] = headers

        self.pricePrec, self.qtyPrec = price_prec, qty_prec
        self.priceMult, self.qtyMult = 10**self.pricePrec, 10**self.qtyPrec

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

        if isinstance(value, float) or isinstance(value, float64):
            return round(value * self.priceMult)
        else:
            return (self.center - value) + self.nBasePrice

    def to_nQty(self, qty: float) -> int:
        """Converts float quantity to fixed-point int scaling representation."""

        return round(qty * self.qtyMult)

    def to_price(self, nPrice: int | int64) -> float | float64:
        """Converts fixed-point price int to floating-point representation."""

        return nPrice / self.priceMult

    def to_qty(self, nQty: int | int64) -> float | float64:
        """Converts fixed-point quantity int to floating-point representation."""

        return nQty / self.qtyMult

    def to_strftime(self, timestamp_ms: int | int64) -> str:
        """Formats millisecond timestamp as ISO-8601 UTC string."""

        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H-%M-%S"
        )

    def get_price(self, idy: int | int64) -> float:
        """Returns rounded float price for specified Footprint row index Y."""

        return round(
            self.to_price(self.to_nPrice(idy)),
            ndigits=self.pricePrec,
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

    # Headers
    def _get_header(self, idx: int | int64, header: c.BarHeaders) -> int64:
        """Extracts header value for specified bar index and BarHeaders field."""

        return self.headers[(idx & ~1) // 2, header]

    # OHLC
    def openNprice(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Open)

    def highNprice(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.High)

    def lowNprice(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Low)

    def closeNprice(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Close)

    def openTime(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.OpenTime)

    def lastTradeTime(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.LastTradeTime)

    # Indicators
    def countTrade(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.CountTrade)

    def volume(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Volume)

    def delta(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.Delta)

    def cvd(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.CVD)

    def vwap(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VWAP)

    def vwap_bb_lower(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VWAP_BB_LOWER)

    def vwap_bb_upper(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VWAP_BB_UPPER)

    def atr(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.ATR)

    def poc(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.POC)

    def vah(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VAH)

    def val(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=c.BarHeaders.VAL)
