from numpy import int32, int64
from numpy.typing import NDArray

from src import FootprintReader
from src import constant as c
from src.typing import AgentManager, Sync


class IntraDay(FootprintReader):
    def __init__(self, manager: AgentManager, sync: Sync) -> None:
        super().__init__(manager=manager, sync=sync)
        self.algorithm_metadata.resize((100_000, 4))
        self.temp = 0

    def update_closed_bar_and_fp(self) -> None:
        super().update_closed_bar_and_fp()
        self.check_pattern()

    def open_position(
        self,
        is_long: bool,
        is_market: bool,
        pass_lag: bool,
        idy: int64,
        idx: int | None,
        ms: int | None,
    ) -> None:
        nPrice = int(self.con.to_nPrice(idy))
        _idx = idx if (idx is not None) else self.last_idx
        _ms = ms if (ms is not None) else int(self.con.lastTradeTime(_idx))
        self.sync.send_signal(
            nPrice=nPrice,
            time_ms=_ms,
            is_long=True if is_long else False,
            is_buy=True if is_long else False,
            is_market=True if is_market else False,
            pass_lag=True if pass_lag else False,
        )
        self.temp += 1

    def check_pattern(self) -> None:
        idx, _ = self.last_idx, self.con

        OPEN: int64 = _.to_idy(_.openNprice(idx))
        HIGH: int64 = _.to_idy(_.highNprice(idx))
        LOW: int64 = _.to_idy(_.lowNprice(idx))
        CLOSE: int64 = _.to_idy(_.closeNprice(idx))
        _VAH, POC, VAL = _.vah(idx), _.poc(idx), _.val(idx)

        # fpStates = self.fp_state_mask(IDYmin=_HIGH, IDYmax=_LOW + 1)
        barStates = self.bar_state_mask(IDYmin=HIGH, IDYmax=LOW + 1, idxBid=idx)
        _bid, _ask = barStates[:, 0], barStates[:, 1]

        if self.p_shape(OPEN, HIGH, LOW, CLOSE, POC, VAL):
            # if self.cachedStatesData[c.CSD_VWAP] > CLOSE:
            self.open_position(
                is_long=False,
                is_market=True,
                pass_lag=True,
                idy=CLOSE,
                idx=idx,
                ms=None,
            )

    def bar_state_mask(
        self, IDYmin: int64, IDYmax: int64, idxBid: int
    ) -> NDArray[int32]:
        bar_flags = (
            c.SF_OPEN
            | c.SF_HIGH
            | c.SF_LOW
            | c.SF_CLOSE
            | c.SF_POC_BAR
            | c.SF_VAH_BAR
            | c.SF_VAL_BAR
        )
        bid_ask_flags = (
            c.SF_DELTA_DOMINATION
            | c.SF_IMBALANCE
            | c.SF_ZERO_PRINT
            | c.SF_FINISHED_AUCTION
            | c.SF_UNFINISHED_AUCTION
        )
        mask = bar_flags | bid_ask_flags
        return self.fp_state[IDYmin:IDYmax, idxBid : idxBid + 2] & mask

    def fp_state_mask(self, IDYmin: int64, IDYmax: int64) -> NDArray[int32]:
        state = c.SF_FINISHED_AUCTION | c.SF_UNFINISHED_AUCTION
        return self.fp_state[IDYmin:IDYmax, self.con.idxVP] & state

    def finished_auction(self, bid: NDArray[int32], ask: NDArray) -> None | bool:
        high_auction_is_finished = bool(ask[0] & c.SF_FINISHED_AUCTION)
        low_auction_is_finished = bool(bid[-1] & c.SF_FINISHED_AUCTION)
        if high_auction_is_finished or low_auction_is_finished:
            return True if low_auction_is_finished else False

    def p_shape(self, O, H, L, C, POC, VAL) -> bool | None:  # noqa : E741
        if (L - H) > (O * 0.003):
            if (POC - H) < ((L - H) * 0.3):
                return True if (C > POC) else False
