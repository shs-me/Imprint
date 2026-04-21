from multiprocessing.synchronize import Event

import numpy as np
from numpy.typing import NDArray

from core.engine.analytical_tools import FootprintReader
from core.settings import BarHeaders as bh  # noqa: F401
from core.settings import StateFlags as sf
from core.utils.monitoring import AgentManager


class IntraDay(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)

    def _update_fp_static_state(self) -> None:
        super()._update_fp_static_state()
        self.check_pattern()

    def check_pattern(self):
        lidx, to = self.last_idx, self.con.get_price
        barStates = self.bar_state_mask(bar=lidx)
        HIGH: np.intp = (barStates[:, 0] & sf.HIGH).argmax()
        LOW: np.intp = (barStates[:, 0] & sf.LOW).argmax()
        bid, ask = barStates[HIGH : LOW + 1, 0], barStates[HIGH : LOW + 1, 1]
        OPEN: np.intp = (bid & sf.OPEN).argmax() + HIGH
        CLOSE: np.intp = (bid & sf.CLOSE).argmax() + HIGH

        VAH: np.intp = (bid & sf.VAH_BAR).argmax() + HIGH
        POC: np.intp = (bid & sf.POC_BAR).argmax() + HIGH
        VAL: np.intp = (bid & sf.VAL_BAR).argmax() + HIGH

        fpStates = self.fp_state_mask(IDYmin=HIGH, IDYmax=LOW + 1)
        HIGH_AUCTION = fpStates[0] & (sf.FINISHED_AUCTION | sf.UNFINISHED_AUCTION)
        LOW_AUCTION = fpStates[-1] & (sf.FINISHED_AUCTION | sf.UNFINISHED_AUCTION)

        if self.P_shape(HIGH=HIGH, LOW=LOW, VAL=VAL):
            if CLOSE > VAL:
                print(
                    f"P-shape-Long[O:{to(OPEN)}|H:{to(HIGH)}|L:{to(LOW)}|C:{to(CLOSE)}|VAH:{to(VAH)}|POC:{to(POC)}|VAL:{to(VAL)} | TIME{self.con.get_time(lidx, strftime=True)}",
                    flush=True,
                )

    def bar_state_mask(self, bar: int) -> NDArray[np.int32]:
        bar_flags = (
            sf.OPEN | sf.HIGH | sf.LOW | sf.CLOSE | sf.POC_BAR | sf.VAH_BAR | sf.VAL_BAR
        )
        bid_ask_flags = sf.DELTA_DOMINATION | sf.IMBALANCE | sf.ZERO_PRINT
        return self.fp_state[:, bar : bar + 2] & (bar_flags | bid_ask_flags)

    def fp_state_mask(self, IDYmin: np.intp, IDYmax: np.intp) -> NDArray[np.int32]:
        state = sf.FINISHED_AUCTION | sf.UNFINISHED_AUCTION
        return self.fp_state[IDYmin:IDYmax, self.con.idxVP] & state

    def P_shape(self, HIGH: np.intp, LOW: np.intp, VAL: np.intp) -> bool:
        if LOW - VAL >= ((LOW - HIGH) * 0.7):
            return True

        return False

    def b_shape(self, HIGH: np.intp, LOW: np.intp, VAH: np.intp) -> bool:
        if VAH - HIGH >= ((LOW - HIGH) * 0.7):
            return True

        return False
