from dataclasses import dataclass, field
from typing import override

from numpy import bool_, int64

from imprint.api.setup import FootprintEngine


@dataclass
class IntraDay(FootprintEngine):
    alpha: int = field(default=1, init=False)
    stop_prev: int64 | int = field(default=0, init=False)
    pos_prev: int64 | int = field(default=0, init=False)

    @override
    def __post_init__(self) -> None:
        FootprintEngine.__post_init__(self)

        self.tick_by_tick_analyze: bool = False

    @override
    def on_clusters_update(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None: ...

    @override
    def on_bar_update(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None: ...

    @override
    def on_bar_close(self) -> None:
        lidx = self.last_idx[0]
        if not ((lidx & ~1) // 2) > (10):
            return

        curr_atr: int64 = self.fp.bar[lidx].ind.atr
        curr_close: int64 = self.fp.bar[lidx].ind.close.n
        pre_close: int64 = self.fp.bar[lidx - 2].ind.close.n

        nLoss: int64 = self.alpha * curr_atr
        if curr_close > self.stop_prev and pre_close > self.stop_prev:
            stop_curr = max(self.stop_prev, curr_close - nLoss)

        elif curr_close < self.stop_prev and pre_close < self.stop_prev:
            stop_curr = min(self.stop_prev, curr_close + nLoss)

        elif curr_close > self.stop_prev:
            stop_curr = curr_close - nLoss

        else:
            stop_curr = curr_close + nLoss

        if pre_close < self.stop_prev and curr_close > stop_curr:
            pos_curr = 1
        elif pre_close > self.stop_prev and curr_close < stop_curr:
            pos_curr = -1
        else:
            pos_curr = self.pos_prev

        above: bool_ = (curr_close > stop_curr) and (
            pre_close <= self.stop_prev
        )
        below: bool_ = (curr_close < stop_curr) and (
            pre_close >= self.stop_prev
        )

        if (curr_close > stop_curr) and above:
            _ = self.send_signal(
                True, True, True, self.fp.bar[lidx].ind.close.id
            )

        if (curr_close < stop_curr) and below:
            _ = self.send_signal(
                True, False, False, self.fp.bar[lidx].ind.close.id
            )

        self.stop_prev = stop_curr
        self.pos_prev = pos_curr
