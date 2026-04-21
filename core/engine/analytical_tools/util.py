from datetime import datetime, timezone
from types import MethodType
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ...configurations import ConfigurationFootprint
from ...settings import BarHeaders as chs


class ConvertMetrics:
    def __init__(
        self,
        trade_param: memoryview,
        footprint: NDArray[np.int64],
        headers: NDArray[np.int64],
        cfgFootprint: ConfigurationFootprint,
    ) -> None:
        self.trade_par = trade_param
        self.footprint = footprint
        self.headers = headers
        self.fpLines = cfgFootprint.fpLines
        self.fpCols = cfgFootprint.fpCols
        self.fpPanelCols = cfgFootprint.fpPanelCols
        self.BarCount = cfgFootprint.bar_count
        self.ims = cfgFootprint.intervalMs
        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult = 10**self.pricePrec + 1e-9
        self.qtyMult = 10**self.qtyPrec + 1e-9
        self.idxVP = cfgFootprint.colVP
        self.idxDP = cfgFootprint.colDP

    def init_session(self, price: float | int, timestamp: int):
        self.nBasePrice = self.to_nPrice(price) if isinstance(price, float) else price
        self.baseTimestamp = timestamp
        if self.nBasePrice >= round(number=self.fpLines * 0.8):
            return False

        else:
            self.center: int = (
                self.nBasePrice
                if self.nBasePrice >= (self.fpLines - self.nBasePrice)
                else (self.fpLines - self.nBasePrice)
            )
            return True

    def check_bound_idy(self, idy: int) -> int | None:
        if 0 <= idy < self.fpLines:
            return idy
        else:
            return None

    def check_bound_idx(self, idx: int) -> int | None:
        if 0 <= idx < self.fpCols:
            return idx
        else:
            return None

    def to_idy(self, nPrice: int) -> int | None:
        return self.check_bound_idy(self.nBasePrice - nPrice + self.center)

    def to_idx(self, timestamp: int, is_sell: bool) -> int | None:
        return self.check_bound_idx(
            (timestamp - self.baseTimestamp) // self.ims * 2 + (0 if is_sell else 1)
        )

    def to_nPrice(self, price: float) -> int:
        return round(price * self.priceMult)

    def to_price(self, nPrice: int) -> float:
        return nPrice / self.priceMult

    def to_nQty(self, qty: float) -> int:
        return round(qty * self.qtyMult)

    def to_qty(self, nQty: int | np.intp) -> float:
        return nQty / self.qtyMult

    def to_strftime(self, timestamp_ms: int) -> str:
        return datetime.fromtimestamp(timestamp_ms // 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def get_price(self, idy: int, normalized: bool = True) -> Any:
        if normalized:
            return self.center - idy + self.nBasePrice
        else:
            return self.to_price(self.center - idy + self.nBasePrice)

    def get_qty(self, idy: int, idx: int, normalized: bool = True) -> Any:
        if normalized:
            return self.footprint[idy, idx]
        else:
            return self.to_qty(self.footprint[idy, idx])

    def get_time(self, idx: int, strftime: bool = False) -> int | str:
        if strftime:
            return self.to_strftime((idx & ~1) // 2 * self.ims + self.baseTimestamp)
        else:
            return (idx & ~1) // 2 * self.ims + self.baseTimestamp

    def get_Bar_id(self, idx: int | None = None) -> int | np.intp:
        if idx is not None:
            return (idx & ~1) // 2
        else:
            return self.headers[:, chs.Open].argmin() - 1

    # Headers
    def _get_header(
        self, idx: int | None, norm: bool, typeNorm: MethodType, header: chs
    ) -> Any:
        if norm:
            return self.headers[self.get_Bar_id(idx), header]
        else:
            return typeNorm(self.headers[self.get_Bar_id(idx), header])

    # OHLC
    def openPrice(self, idx: int | None = None, normalized: bool = True) -> Any:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_price, header=chs.Open
        )

    def highPrice(self, idx: int | None = None, normalized: bool = True) -> Any:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_price, header=chs.High
        )

    def lowPrice(self, idx: int | None = None, normalized: bool = True) -> Any:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_price, header=chs.Low
        )

    def closePrice(self, idx: int | None = None, normalized: bool = True) -> Any:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_price, header=chs.Close
        )

    # BaseMetrics
    def openTime(self, idx: int | None = None, strftime: bool = False) -> int | str:
        return self._get_header(
            idx=idx, norm=strftime, typeNorm=self.to_strftime, header=chs.Time
        )

    def countTrade(self, idx: int | None = None) -> int:
        return self._get_header(
            idx=idx, norm=True, typeNorm=self.to_price, header=chs.CountTrade
        )

    def volume(self, idx: int | None = None, normalized: bool = True) -> Any:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_qty, header=chs.Volume
        )

    # Indicators
    def cvd(self, idx: int | None = None, normalized: bool = True) -> Any:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_qty, header=chs.CVD
        )

    def delta(self, idx: int | None = None, normalized: bool = True) -> Any:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_qty, header=chs.Delta
        )

    # Settings indicators
    def vwap_sum_p2w(self, idx: int | None = None, normalized: bool = True) -> int:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_qty, header=chs.VWAP_P2W
        )

    def vwap_sum_pw(self, idx: int | None = None, normalized: bool = True) -> int:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_qty, header=chs.VWAP_PW
        )

    def vwap_sum_w(self, idx: int | None = None, normalized: bool = True) -> int:
        return self._get_header(
            idx=idx, norm=normalized, typeNorm=self.to_qty, header=chs.VWAP_W
        )
