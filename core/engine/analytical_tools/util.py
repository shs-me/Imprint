from datetime import datetime, timezone
from typing import overload

import numpy as np
from numpy import float64, int64
from numpy.typing import NDArray

from ...configurations import ConfigurationFootprint
from ...settings import BarHeaders as chs


class ConvertMetrics:
    def __init__(
        self,
        footprint: NDArray[int64],
        headers: NDArray[int64],
        trade_param: memoryview,
        cfgFP: ConfigurationFootprint,
    ) -> None:
        self.footprint, self.headers = footprint, headers
        self.trade_par = trade_param
        self.fpLines, self.fpCols = cfgFP.fpLines, cfgFP.fpCols
        self.fpPanelCols, self.barCount = cfgFP.fpPanelCols, cfgFP.bar_count
        self.ims = cfgFP.intervalMs
        self.idxVP, self.idxDP = cfgFP.colVP, cfgFP.colDP

        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult: float = (10**self.pricePrec) + 1e-9
        self.qtyMult: float = 10**self.qtyPrec + 1e-9

    def init_session(self, price: float | int, timestamp: int):
        self.nBasePrice: int = (
            self.to_nPrice(price) if isinstance(price, float) else price
        )
        self.baseTimestamp: int = timestamp
        if self.nBasePrice >= round(number=self.fpLines * 0.8):
            return False

        else:
            self.center: int = (
                self.nBasePrice
                if self.nBasePrice >= (self.fpLines - self.nBasePrice)
                else (self.fpLines - self.nBasePrice)
            )
            return True

    @overload
    def to_idy(self, nPrice: int) -> int | None: ...
    @overload
    def to_idy(self, nPrice: int64) -> int64: ...
    def to_idy(self, nPrice):
        idy: int | int64 = (self.nBasePrice - nPrice) + self.center
        if 0 <= idy < self.fpLines:
            return idy
        else:
            return None

    def to_idx(self, timestamp: int, is_sell: bool) -> int | None:
        idx: int = (timestamp - self.baseTimestamp) // self.ims * 2 + (
            0 if is_sell else 1
        )
        if 0 <= idx < self.fpCols:
            return idx
        else:
            return None

    def to_nPrice(self, price: float) -> int:
        return round(price * self.priceMult)

    def to_nQty(self, qty: float) -> int:
        return round(qty * self.qtyMult)

    def to_price(self, nPrice: int | int64) -> float | float64:
        return nPrice / self.priceMult

    def to_qty(self, nQty: int | int64) -> float | float64:
        return nQty / self.qtyMult

    def to_strftime(self, timestamp_ms: int | int64) -> str:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def get_price(self, idy: int | int64) -> float:
        return round(
            self.to_price((self.center - idy) + self.nBasePrice),
            ndigits=self.pricePrec,
        )

    def get_qty(self, idy: int, idx: int) -> float:
        return self.to_qty(self.footprint[idy, idx])

    @overload
    def get_time(self, idx: int64, strftime: bool = False) -> int64: ...
    @overload
    def get_time(self, idx: int, strftime: bool = True) -> str: ...
    def get_time(self, idx: int | int64, strftime: bool = False):
        if strftime:
            return self.to_strftime((idx & ~1) // 2 * self.ims + self.baseTimestamp)
        else:
            return (idx & ~1) // 2 * self.ims + self.baseTimestamp

    # Headers
    def _get_header(self, idx: int | int64, header: chs) -> int64:
        return self.headers[(idx & ~1) // 2, header]

    # OHLC
    def openIdy(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.Open)

    def highIdy(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.High)

    def lowIdy(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.Low)

    def closeIdy(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.Close)

    def openTime(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.Time)

    # Indicators
    def countTrade(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.CountTrade)

    def volume(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.Volume)

    def delta(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.Delta)

    def cvd(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.CVD)

    def vwap(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.VWAP)

    def vwap_bb_lower(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.VWAP_BB_LOWER)

    def vwap_bb_upper(self, idx: int | int64) -> int64:
        return self._get_header(idx=idx, header=chs.VWAP_BB_UPPER)
