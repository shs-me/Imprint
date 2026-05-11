from multiprocessing.synchronize import Event

from numpy import int32, int64
from numpy.typing import NDArray

from core.engine.agents_utils.logic.footprint_reader import FootprintReader
from core.settings import StateFlags as sf
from core.utils.monitoring.agent_manager import AgentManager


class IntraDay(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)
        self.algorithm_metadata.resize((1500, 4))
        self.row = 0

    def _update_closed_bar_and_fp(self) -> None:
        super()._update_closed_bar_and_fp()
        self.check_pattern()

    def check_pattern(self) -> None:
        idx, _ = self.last_idx, self.con

        _OPEN: int64 = _.to_idy(_.openNprice(idx))
        _HIGH: int64 = _.to_idy(_.highNprice(idx))
        _LOW: int64 = _.to_idy(_.lowNprice(idx))
        _CLOSE: int64 = _.to_idy(_.closeNprice(idx))
        _VAH, _POC, _VAL = _.vah(idx), _.poc(idx), _.val(idx)

        fpStates = self.fp_state_mask(IDYmin=_HIGH, IDYmax=_LOW + 1)
        barStates = self.bar_state_mask(IDYmin=_HIGH, IDYmax=_LOW + 1, idxBid=idx)
        _bid, _ask = barStates[:, 0], barStates[:, 1]

        high_auction_is_finished = bool(fpStates[0] & sf.FINISHED_AUCTION)
        low_auction_is_finished = bool(fpStates[-1] & sf.FINISHED_AUCTION)

        if high_auction_is_finished or low_auction_is_finished:
            if high_auction_is_finished:
                self.algorithm_metadata[self.row, 0] = _.openTime(idx)
                self.algorithm_metadata[self.row, 1] = _.to_nPrice(_CLOSE)
                self.send_signal(
                    nPrice=int(_.to_nPrice(_CLOSE)),
                    time_ms=_.time_ms(idx),
                    is_long=False,
                    is_buy=False,
                )

            if low_auction_is_finished:
                self.algorithm_metadata[self.row, 0] = _.openTime(idx)
                self.algorithm_metadata[self.row, 2] = _.to_nPrice(_CLOSE)
                self.send_signal(
                    nPrice=int(_.to_nPrice(_CLOSE)),
                    time_ms=_.time_ms(idx),
                    is_long=True,
                    is_buy=True,
                )

            self.row += 1

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
