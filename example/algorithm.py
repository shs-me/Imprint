from dataclasses import dataclass, field
from typing import override

from numpy import int64

from imprint import constant as c
from imprint.configs import FootprintEngine


@dataclass(slots=True)
class IntraDay(FootprintEngine):
    ma_volume_period: int = field(default=50, init=False)
    ma_avg_trade_size_period: int = field(default=50, init=False)
    big_cluster_mult: float = field(default=0.7, init=False)

    idy_use: int | int64 = field(default=0, init=False)
    idx_use: int | int64 = field(default=0, init=False)

    @override
    def on_bar_update(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        if not ((idxBid // 2) > (50)):
            return

        if (self.idx_use == idxBid) and (self.idy_use == idYmin):
            return

        bar = self.fp.bar[idxBid]
        idy = idYmin - bar.ind.high.id

        bid, ask = bar.base[idy, :]
        bid_state, ask_state = bar.state[idy, :]
        bid_ctrade, ask_ctrade = bar.ctrade[idy, :]

        if ask_state & c.SF_BIG_CLUSTER:
            self.idx_use, self.idy_use = idxBid, idYmin
            if ask_state & c.SF_IMBALANCE and (
                (self.fp.bar[idxBid - 2].ind.ma_avg_trade_size * 10)
                < (ask // ask_ctrade)
            ):
                self.send_signal(False, True, True, idYmin)
