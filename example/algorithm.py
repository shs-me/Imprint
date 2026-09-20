from dataclasses import dataclass, field
from typing import override

from numpy import int64

from imprint import constant as c
from imprint.configs import FootprintEngine


@dataclass(slots=True)
class IntraDay(FootprintEngine):
    idy_use: int | int64 = field(default=0, init=False)
    idx_use: int | int64 = field(default=0, init=False)

    @override
    def on_bar_update(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        if not ((idxBid // 2) > (24)):
            return

        if (self.idx_use == idxBid) and (self.idy_use == idYmin):
            return

        bar = self.fp.bar[idxBid]
        idy = idYmin - bar.ind.high.id
        bid, ask = bar.state[idy, :]

        if ask & c.SF_BIG_TRADE and ask & c.SF_IMBALANCE:
            self.idx_use, self.idy_use = idxBid, idYmin
            self.send_signal(False, False, False, idYmin)

        elif bid & c.SF_BIG_TRADE and bid & c.SF_IMBALANCE:
            self.idx_use, self.idy_use = idxBid, idYmin
            self.send_signal(False, True, True, idYmin)
