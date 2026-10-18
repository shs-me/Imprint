from dataclasses import dataclass, field
from typing import override

import numpy as np

from imprint import StrategyEngine, c


@dataclass(slots=True)
class IntraDay(StrategyEngine):
    ma_volume_period: int = field(default=21, init=False)
    ma_avg_trade_size_period: int = field(default=21, init=False)
    big_cluster_mult: float = field(default=0.3, init=False)

    @override
    def on_bar_close(self, idx: int, lidx: int) -> None:
        if not ((lidx // 2) > (20)):
            return

        bar = self.fp[lidx]
        if bar.is_empty:
            return

        ind = bar.ind
        atr_pct = ind.atr_percent
        if ((atr_pct) > 0.001) and np.any(bar.state & c.SF_BIG_CLUSTER):
            OPEN, HIGH = ind.open.n, ind.high.n
            LOW, CLOSE = ind.low.n, ind.close.n
            POC = bar.vp.poc.n
            FP_POC, FP_VAH, FP_VAL = (
                ind.fp_poc.n,
                ind.fp_vah.n,
                ind.fp_val.n,
            )
            VWAP = ind.fp_vwap.n
            if ind.delta_ratio > 0.3 and CLOSE > POC:
                self.send_signal(
                    False,
                    True,
                    True,
                    CLOSE,
                    tp_dev=round(atr_pct * 10000 * 8),
                    sl_dev=round(atr_pct * 10000 * 4),
                )
