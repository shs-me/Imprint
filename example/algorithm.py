from dataclasses import dataclass, field
from typing import override

from numpy import int64

from imprint import constant as c
from imprint.configs import FootprintEngine


@dataclass(slots=True)
class IntraDay(FootprintEngine):
    idy_use: int | int64 = field(default=0, init=False)
    idx_use: int | int64 = field(default=0, init=False)
    need_states: int = field(
        default=c.SF_POC_BAR
        | c.SF_POC_FP
        | c.SF_VWAP_FP
        | c.SF_VAH_BAR
        | c.SF_VAL_BAR
        | c.SF_VAH_FP
        | c.SF_VAL_FP,
        init=False,
    )

    @override
    def on_bar_update(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        if not ((idxBid // 2) > (60 * 4)):
            return

        if (self.idy_use == idYmin) and (self.idx_use == idxBid):
            return

        bar = self.fp.bar[idxBid]
        bar_base = bar.base
        idy = idYmin - bar.ind.high.id
        avg_vol = bar.ind.avg_volume(4 * 60)

        if (bar_base[idy, 1] > (avg_vol * 0.3)) and (
            bar.state[idy, 1] & c.SF_IMBALANCE
        ):
            self.idy_use, self.idx_use = idYmin, idxBid
            self.send_signal(True, True, True, idYmin)

        elif (bar_base[idy, 0] > (avg_vol * 0.3)) and (
            bar.state[idy, 0] & c.SF_IMBALANCE
        ):
            self.idy_use, self.idx_use = idYmin, idxBid
            self.send_signal(True, False, False, idYmin)
