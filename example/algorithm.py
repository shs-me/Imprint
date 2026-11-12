from dataclasses import dataclass, field
from typing import override

import numpy as np

from imprint import StrategyEngine, c


@dataclass(slots=True)
class IntraDay(StrategyEngine):
    ma_volume_period: int = field(default=10, init=False)
    ma_avg_trade_size_period: int = field(default=21, init=False)
    big_cluster_vol: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )

    @override
    def on_bar_close(self, closed_bar_id: int, last_bar_id: int) -> None:
        if not ((closed_bar_id // 2) > (12)):
            return

        bar = self.fp[closed_bar_id]
        if bar.is_empty:
            return

        ind, vp = bar.ind, bar.vp
        atr_pct = ind.atr_percent
        if atr_pct < 0.0025:
            return

        CLOSE, HIGH = ind.close, ind.high
        POC = vp.poc
        if ind.fp_vwap_up_band.n > POC.n > CLOSE.n:
            poc_bar = POC.y - HIGH.y
            has_traped_buyers = np.any(
                bar.base[0 : poc_bar + 1, 2] & c.SF_BIG_CLUSTER
            )
            if has_traped_buyers:
                self.send_signal(
                    True,
                    False,
                    False,
                    CLOSE.n,
                    tp_dev=round(atr_pct * 10000 * 2),
                    sl_dev=round(atr_pct * 10000 * 4),
                )

        elif CLOSE.n > POC.n > ind.fp_vwap_low_band.n:
            poc_bar = POC.y - HIGH.y
            has_traped_buyers = np.any(
                bar.base[0 : poc_bar + 1, 0] & c.SF_BIG_CLUSTER
            )
            if has_traped_buyers:
                self.send_signal(
                    True,
                    True,
                    True,
                    CLOSE.n,
                    tp_dev=round(atr_pct * 10000 * 2),
                    sl_dev=round(atr_pct * 10000 * 4),
                )
