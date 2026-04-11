from datetime import datetime, timezone

import numpy as np
from numpy.typing import NDArray

from ...configurations import ConfigurationFootprint
from ...settings import ClusterHeaders as chs


class ConvertMetrics:
    def __init__(
        self,
        trade_param: memoryview,
        footprint: NDArray[np.int64],
        headers_buf: memoryview,
        cfgFootprint: ConfigurationFootprint,
    ) -> None:
        self.trade_par = trade_param
        self.footprint = footprint
        self.headers_buf = headers_buf
        self.lines = cfgFootprint.lines
        self.footprintCols = cfgFootprint.footprintCols
        self.panelCols = cfgFootprint.panelCols
        self.clusterCount = cfgFootprint.cluster_count
        self.ims = cfgFootprint.intervalMs
        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult, self.qtyMult = 10**self.pricePrec, 10**self.qtyPrec
        self.cluster_id = 0

        self.idxVP = cfgFootprint.colVP
        self.idxBidVP = cfgFootprint.colBidVP
        self.idxAskVP = cfgFootprint.colAskVP

    def _init_array(self):
        self.headers: NDArray[np.int64] = np.ndarray(
            shape=(self.clusterCount, chs._HeadersCount),
            dtype=np.int64,
            buffer=self.headers_buf,
        )

    def init_session(self, price: float | int, timestamp: int):
        self.nBasePrice = self.to_nPrice(price) if isinstance(price, float) else price
        self.baseTimestamp = timestamp
        if self.nBasePrice >= round(number=self.lines * 0.8):
            return False

        else:
            self.center: int = (
                self.nBasePrice
                if self.nBasePrice >= (self.lines - self.nBasePrice)
                else (self.lines - self.nBasePrice)
            )
            return True

    def check_bound_idy(self, idy: int) -> int | None:
        if 0 < idy < self.lines:
            return idy
        else:
            return None

    def check_bound_idx(self, idx: int) -> int | None:
        if 0 <= idx < self.footprintCols:
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

    def get_price(self, idy: int, normalized: bool = True) -> int | float:
        if normalized:
            return self.center - idy + self.nBasePrice
        else:
            return self.to_price(self.center - idy + self.nBasePrice)

    def get_qty(self, idy: int, idx: int, normalized: bool = True) -> int | float:
        if normalized:
            return self.footprint[idy, idx]
        else:
            return self.to_qty(self.footprint[idy, idx])

    def get_time(self, idx: int, strftime: bool = False) -> int | str:
        if strftime:
            return self.to_strftime(
                (idx - (0 if (idx % 2) == 0 else 1)) // 2 * self.ims
                + self.baseTimestamp
            )
        else:
            return (
                idx - (0 if (idx % 2) == 0 else 1)
            ) // 2 * self.ims + self.baseTimestamp

    def get_cluster_id(self, idx: int) -> int:
        return ((idx - 1) // 2) if (idx % 2) != 0 else (idx // 2)


class Indicators:
    def __init__(
        self,
        converter: ConvertMetrics,
    ) -> None:
        self.cv = converter

    def _get_data(self, header: chs, idx: int | None) -> int:
        if idx:
            cid = self.cv.get_cluster_id(idx) * chs._HeadersCount
            return self.cv.headers_buf[cid + header]
        else:
            cid = (self.cv.headers[:, chs.Open].argmin() - 1) * chs._HeadersCount
            return self.cv.headers_buf[cid + header]

    def _get_header(
        self, idx: int | None, norm: bool, price: bool, header: chs
    ) -> int | float:
        func = self.cv.to_price if price else self.cv.to_qty
        if norm:
            return self._get_data(header=header, idx=idx)
        else:
            return func(self._get_data(header=header, idx=idx))

    # OHLC
    def openPrice(self, idx: int | None = None, normalized: bool = True) -> int | float:
        return self._get_header(idx=idx, norm=normalized, price=False, header=chs.Open)

    def highPrice(self, idx: int | None = None, normalized: bool = True) -> int | float:
        return self._get_header(idx=idx, norm=normalized, price=False, header=chs.High)

    def lowPrice(self, idx: int | None = None, normalized: bool = True) -> int | float:
        return self._get_header(idx=idx, norm=normalized, price=False, header=chs.Low)

    def closePrice(
        self, idx: int | None = None, normalized: bool = True
    ) -> int | float:
        return self._get_header(idx=idx, norm=normalized, price=False, header=chs.Close)

    # BaseMetrics
    def openTime(self, idx: int | None = None, strftime: bool = False) -> int | str:
        if strftime:
            return self.cv.to_strftime(self._get_data(header=chs.Time, idx=idx))
        else:
            return self._get_data(header=chs.Time, idx=idx)

    def countTrade(self, idx: int | None = None) -> int:
        return self._get_data(header=chs.CountTrade, idx=idx)

    def volume(self, idx: int | None = None, normalized: bool = True) -> int | float:
        return self._get_header(
            idx=idx, norm=normalized, price=False, header=chs.Volume
        )

    # Indicators
    def cvd(self, idx: int | None = None, normalized: bool = True) -> int | float:
        return self._get_header(idx=idx, norm=normalized, price=False, header=chs.CVD)

    def vwap(self, idx: int | None = None, normalized: bool = True) -> int | float:
        return self._get_header(idx=idx, norm=normalized, price=False, header=chs.VWAP)

    def delta(self, idx: int | None = None, normalized: bool = True) -> int | float:
        return self._get_header(idx=idx, norm=normalized, price=False, header=chs.Delta)

    def poc(
        self,
        idx: int | None = None,
        index: bool = True,
    ) -> np.int64 | np.intp:
        func = np.argmax if index else np.max
        if idx:
            return func(self.cv.footprint[:, idx])
        else:
            return func(self.cv.footprint[:, self.cv.idxVP])
