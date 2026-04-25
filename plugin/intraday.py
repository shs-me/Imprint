from multiprocessing.synchronize import Event

from numpy import int32, int64, intp
from numpy.typing import NDArray

from core.engine.analytical_tools.footprint.footprint_reader import FootprintReader
from core.settings import StateFlags as sf
from core.utils.monitoring.agent_manager import AgentManager


class IntraDay(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)

    def _update_fp_static_state(self) -> None:
        super()._update_fp_static_state()
        self.check_pattern()

    def check_pattern(self) -> None:
        lidx, _ = self.last_idx, self.con

        OPEN: int64 = _.openIdy(lidx)
        HIGH: int64 = _.highIdy(lidx)
        LOW: int64 = _.lowIdy(lidx)
        CLOSE: int64 = _.closeIdy(lidx)

        fpStates = self.fp_state_mask(IDYmin=HIGH, IDYmax=LOW + 1)
        barStates = self.bar_state_mask(IDYmin=HIGH, IDYmax=LOW + 1, idxBid=lidx)
        bid, ask = barStates[:, 0], barStates[:, 1]

        VAH: intp = (bid & sf.VAH_BAR).argmax() + HIGH
        POC: intp = (bid & sf.POC_BAR).argmax() + HIGH
        VAL: intp = (bid & sf.VAL_BAR).argmax() + HIGH

        HIGH_AUCTION = fpStates[0] & (sf.FINISHED_AUCTION | sf.UNFINISHED_AUCTION)
        LOW_AUCTION = fpStates[-1] & (sf.FINISHED_AUCTION | sf.UNFINISHED_AUCTION)

        if self.P_shape(HIGH=HIGH, LOW=LOW, VAL=VAL):
            # print(
            #    "P-shape: "
            #    f"O:{_.get_price(OPEN)}"
            #    f" | H:{_.get_price(HIGH)}"
            #    f" | L:{_.get_price(LOW)}"
            #    f" | C:{_.get_price(CLOSE)}"
            #    f" | VAH:{_.get_price(VAH)}"
            #    f" | POC:{_.get_price(POC)}"
            #    f" | VAL:{_.get_price(VAL)}"
            #    f" | TIME:{_.get_time(lidx, strftime=True)}",
            # )
            self.send_signal(
                nPrice=int(_.to_nPrice(CLOSE)),
                time_ms=_.time_ms(),
                long=True,
                buy=True,
                market=True,
            )

        if self.b_shape(HIGH=HIGH, LOW=LOW, VAH=VAH):
            # print(
            #    "b-shape: "
            #    f"O:{_.get_price(OPEN)}"
            #    f" | H:{_.get_price(HIGH)}"
            #    f" | L:{_.get_price(LOW)}"
            #    f" | C:{_.get_price(CLOSE)}"
            #    f" | VAH:{_.get_price(VAH)}"
            #    f" | POC:{_.get_price(POC)}"
            #    f" | VAL:{_.get_price(VAL)}"
            #    f" | TIME:{_.get_time(lidx, strftime=True)}",
            # )
            self.send_signal(
                nPrice=int(_.to_nPrice(CLOSE)),
                time_ms=_.time_ms(),
                long=False,
                buy=False,
                market=True,
            )

    def bar_state_mask(
        self, IDYmin: int64, IDYmax: int64, idxBid: int
    ) -> NDArray[int32]:
        bar_flags = (
            sf.OPEN | sf.HIGH | sf.LOW | sf.CLOSE | sf.POC_BAR | sf.VAH_BAR | sf.VAL_BAR
        )
        bid_ask_flags = sf.DELTA_DOMINATION | sf.IMBALANCE | sf.ZERO_PRINT
        mask = bar_flags | bid_ask_flags
        return self.fp_state[IDYmin:IDYmax, idxBid : idxBid + 2] & mask

    def fp_state_mask(self, IDYmin: int64, IDYmax: int64) -> NDArray[int32]:
        state = sf.FINISHED_AUCTION | sf.UNFINISHED_AUCTION
        return self.fp_state[IDYmin:IDYmax, self.con.idxVP] & state

    def P_shape(self, HIGH: int64, LOW: int64, VAL: intp) -> bool:
        if LOW - VAL >= ((LOW - HIGH) * 0.7):
            return True

        return False

    def b_shape(self, HIGH: int64, LOW: int64, VAH: intp) -> bool:
        if VAH - HIGH >= ((LOW - HIGH) * 0.7):
            return True

        return False
