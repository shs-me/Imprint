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
        if not ((idxBid // 2) > 20):
            return

        if (self.idy_use == idYmin) and (self.idx_use == idxBid):
            return

        bar = self.fp.bar[idxBid]
        avg_vol = bar.ind.avg_volume
        bar_state = bar.state
        bar_base = bar.base
        ind = bar.ind
        idy = idYmin - bar.ind.high.id
        nPrice = self.fp.con.to_nPrice(idYmin)
        if (
            (bar_base[idy, 1] > (avg_vol * 0.25))
            and (bar_state[idy, 1] & c.SF_DELTA_DOMINATION)
            and ((nPrice >= ind.fp_vwap.n) and (nPrice >= ind.fp_poc.n))
        ):
            self.idy_use, self.idx_use = idYmin, idxBid
            self.send_signal(True, True, True, idYmin)
