from dataclasses import dataclass, field
from typing import override

from numpy import bool_, int64

from imprint.api.base import FootprintEngine


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
    def find_patterns_in_update_clusters(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None:
        pass

    @override
    def find_patterns_in_update_bar(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        return

        if not (idxBid // 2) > (20):
            return

        bar = self.fp.bar[idxBid]
        vol = bar.ind.volume
        avg_vol = bar.ind.avg_volume

        if not (vol * 2) > avg_vol:
            return

        bar_idy: int64 = idYmin - bar.ind.high.id

        bar_arr = bar.base
        bid_vol: int64 = bar_arr.bid[bar_idy]
        ask_vol: int64 = bar_arr.ask[bar_idy]

        if (bid_vol > (avg_vol * 0.5)) and (bid_vol > ask_vol):
            _ = self.send_signal(True, False, False, idYmin, idxBid)

        if (ask_vol > (avg_vol * 0.5)) and (ask_vol > bid_vol):
            _ = self.send_signal(True, True, True, idYmin, idxBid)

    @override
    def find_patterns_in_update_closed_bar(self) -> None:
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
