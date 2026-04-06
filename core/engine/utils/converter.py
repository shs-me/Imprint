from datetime import datetime, timezone

from ... import Config


class ConvertMetrics:
    def __init__(
        self,
        trade_param: memoryview,
        nBasePrice: int,
        nBaseTimestamp: int,
    ) -> None:
        __cfg = Config.ShmSharing
        self.trade_par = trade_param
        self.nBasePrice, self.nBaseTimestamp = nBasePrice, nBaseTimestamp
        self.ims = Config.UserConfig.interval_min * 60 * 1000
        self.lines, self.cols = __cfg.Footprint.lines, __cfg.Footprint.cols
        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult, self.qtyMult = 10**self.pricePrec, 10**self.qtyPrec
        self.cluster_id = 0
        self.headers, self.headers_count = (
            __cfg.Footprint.Headers,
            __cfg.Footprint.headers_count,
        )

    def init_center(self):
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
        idx: int = round(number=(timestamp - self.nBaseTimestamp) / self.ims * 2) + (
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
        ) // 2 * self.ims + self.nBaseTimestamp
        return timestamp

    def get_cluster_id(self, idx: int | None = None) -> int:
        hrc = self.headers_count
        if idx is None:
            return self.cluster_id
        else:
            self.cluster_id = ((idx - 1) // 2) if (idx % 2) != 0 else (idx // 2) * hrc
            return self.cluster_id
