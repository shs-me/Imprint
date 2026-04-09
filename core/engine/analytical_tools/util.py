from datetime import datetime, timezone

from ...configurations import ConfigurationFootprint
from ...settings import ClusterHeaders


class ConvertMetrics:
    def __init__(
        self, trade_param: memoryview, cfgFootprint: ConfigurationFootprint
    ) -> None:
        self.trade_par = trade_param
        self.lines, self.cols = cfgFootprint.lines, cfgFootprint.cols
        self.ims = cfgFootprint.intervalMs
        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult, self.qtyMult = 10**self.pricePrec, 10**self.qtyPrec
        self.headers, self.headers_count = ClusterHeaders, ClusterHeaders._HeadersCount
        self.cluster_id = 0

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

    def to_qty(self, nQty: int) -> float:
        return nQty / self.qtyMult

    def to_strftime(self, timestamp: int):
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    def get_idy(self, nPrice: int) -> int | None:
        """IF 0 < ID-Y < Lines, Return ID-Y | Else, Return None"""
        idy: int = self.nBasePrice - nPrice + self.center
        if 0 < idy < self.lines:
            return idy

        else:
            return None

    def get_idx(self, timestamp: int, is_sell: bool) -> int | None:
        idx: int = round(number=(timestamp - self.baseTimestamp) / self.ims * 2) + (
            0 if is_sell else 1
        )
        if 0 <= idx < self.cols:
            return idx
        else:
            return None

    def get_nPrice(self, idy: int) -> int:
        return self.center - idy + self.nBasePrice

    def get_nTimestamp(self, idx: int) -> int:
        timestamp: int = (
            idx - (0 if (idx % 2) == 0 else 1)
        ) // 2 * self.ims + self.baseTimestamp
        return timestamp

    def get_cluster_id(self, idx: int | None = None) -> int:
        hrc = self.headers_count
        if idx is None:
            return self.cluster_id
        else:
            self.cluster_id = ((idx - 1) // 2) if (idx % 2) != 0 else (idx // 2) * hrc
            return self.cluster_id
