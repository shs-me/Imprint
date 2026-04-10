from datetime import datetime, timezone

import numpy as np
from numpy.typing import NDArray

from ...configurations import ConfigurationFootprint
from ...settings import ClusterHeaders as chs


class ConvertMetrics:
    def __init__(
        self,
        trade_param: memoryview,
        cfgFootprint: ConfigurationFootprint,
    ) -> None:
        self.trade_par = trade_param
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

    def to_nPrice(self, price: float) -> int:
        return round(price * self.priceMult)

    def to_nQty(self, qty: float) -> int:
        return round(qty * self.qtyMult)

    def to_price(self, nPrice: int) -> float:
        return nPrice / self.priceMult

    def to_qty(
        self, nQty: int | np.intp | NDArray[np.int64]
    ) -> float | NDArray[np.float64]:
        return nQty / self.qtyMult

    def to_idy(self, nPrice: int) -> int | None:
        idy: int = self.nBasePrice - nPrice + self.center
        if 0 < idy < self.lines:
            return idy

        else:
            return None

    def to_idx(self, timestamp: int, is_sell: bool) -> int | None:
        idx: int = round(number=(timestamp - self.baseTimestamp) / self.ims * 2) + (
            0 if is_sell else 1
        )
        if 0 <= idx < self.footprintCols:
            return idx
        else:
            return None

    def to_strftime(self, timestamp_ms: int) -> str:
        return datetime.fromtimestamp(timestamp_ms // 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def get_nPrice(self, idy: int) -> int:
        return self.center - idy + self.nBasePrice

    def get_nTimestamp(self, idx: int) -> int:
        timestamp: int = (
            idx - (0 if (idx % 2) == 0 else 1)
        ) // 2 * self.ims + self.baseTimestamp
        return timestamp

    def get_cluster_id(self, idx: int) -> int:
        return ((idx - 1) // 2) if (idx % 2) != 0 else (idx // 2)


class Indicators:
    def __init__(
        self,
        footprint: NDArray[np.int64],
        headers_buf: memoryview,
        converter: ConvertMetrics,
    ) -> None:
        self.footprint = footprint
        self.cv = converter
        self.headers_buf = headers_buf
        self._init_array(headers_buf)

    def _init_array(self, headers_buf: memoryview):
        self.headers = np.ndarray(
            (self.cv.clusterCount, chs._HeadersCount),
            dtype=np.int64,
            buffer=headers_buf,
        )

    def poc(
        self,
        idx: int | None = None,
        index: bool = True,
    ) -> np.int64 | np.intp:
        func = np.argmax if index else np.max
        if idx:
            return func(self.footprint[:, idx])
        else:
            return func(self.footprint[:, self.cv.idxVP])

    def get_header(self, header: chs, idx: int | None) -> int:
        if idx:
            cid = self.cv.get_cluster_id(idx) * chs._HeadersCount
            return self.headers_buf[cid + header]
        else:
            cid = (self.headers[:, chs.Open].argmin() - 1) * chs._HeadersCount
            return self.headers_buf[cid + header]

    def cvd(self, idx: int | None = None) -> int:
        return self.get_header(header=chs.CVD, idx=idx)

    def vwap(self, idx: int | None = None) -> int:
        return self.get_header(header=chs.VWAP, idx=idx)

    def delta(self, idx: int | None = None) -> int:
        return self.get_header(header=chs.Delta, idx=idx)

    def volume(self, idx: int | None = None) -> int:
        return self.get_header(header=chs.Volume, idx=idx)

    def openPrice(self, idx: int | None = None) -> int:
        return self.get_header(header=chs.Open, idx=idx)

    def highPrice(self, idx: int | None = None) -> int:
        return self.get_header(header=chs.High, idx=idx)

    def lowPrice(self, idx: int | None = None) -> int:
        return self.get_header(header=chs.Low, idx=idx)

    def closePrice(self, idx: int | None = None) -> int:
        return self.get_header(header=chs.Close, idx=idx)
