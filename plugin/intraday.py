import time
from multiprocessing.synchronize import Event

from numpy import int32, int64, intp
from numpy.typing import NDArray

from core.engine.analytical_tools.footprint.footprint_reader import FootprintReader
from core.settings import OrderFlag as of
from core.settings import StateFlags as sf
from core.utils.monitoring.agent_manager import AgentManager


class IntraDay(FootprintReader):
    def __init__(self, manager: AgentManager, execution_event: Event) -> None:
        super().__init__(manager, execution_event)
        self.strategy_init()

    def strategy_init(self) -> None:
        self.cfgST = self.manager.cfgStrategy
        self.TP = self.cfgST.TP
        self.SL = self.cfgST.SL
        # L/S Buf Setup
        self.cell_amount = self.cfgST.cell_amount
        self.readerId = self.cfgST.reader[1] // 8 - 1
        self.writerId = self.cfgST.writer[1] // 8 - 1
        self.nPriceId = self.cfgST.nPrice[1] // 8 - 1
        self.time_msId = self.cfgST.time_ms[1] // 8 - 1
        self.orderParamId = self.cfgST.orderParam[1] // 8 - 1
        self.signal_size = self.cfgST.signal_size // 8
        self.signal_offset = self.cfgST.offset // 8
        self.longBuf = self.manager.strategy_buf[slice(*self.cfgST.longBuf)].cast("q")
        self.shortBuf = self.manager.strategy_buf[slice(*self.cfgST.shortBuf)].cast("q")

    def send_signal(
        self,
        nPrice: int,
        time_ms: int,
        long: bool,
        buy: bool,
        market: bool,
    ) -> None:
        signal_buf = self.longBuf if long else self.shortBuf

        orderParam = 0
        orderParam |= of.BUY if buy else of.SELL
        orderParam |= of.MARKET if market else of.LIMIT

        cell: int = signal_buf[self.writerId]
        start: int = cell * self.signal_size + self.signal_offset

        signal_buf[start + self.nPriceId] = nPrice
        signal_buf[start + self.time_msId] = time_ms
        signal_buf[start + self.orderParamId] = orderParam

        new_cell = cell + 1
        signal_buf[self.writerId] = new_cell if new_cell < self.cell_amount else 0
        if self.execution_event.is_set() is False:
            self.execution_event.set()

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
            print(
                "P-shape: "
                f"O:{_.get_price(OPEN)}"
                f" | H:{_.get_price(HIGH)}"
                f" | L:{_.get_price(LOW)}"
                f" | C:{_.get_price(CLOSE)}"
                f" | VAH:{_.get_price(VAH)}"
                f" | POC:{_.get_price(POC)}"
                f" | VAL:{_.get_price(VAL)}"
                f" | TIME:{_.get_time(lidx, strftime=True)}",
            )
            self.send_signal(
                nPrice=int(_.to_nPrice(CLOSE)),
                time_ms=(time.time_ns() // 1000),
                long=True,
                buy=True,
                market=True,
            )

        if self.b_shape(HIGH=HIGH, LOW=LOW, VAH=VAH):
            print(
                "b-shape: "
                f"O:{_.get_price(OPEN)}"
                f" | H:{_.get_price(HIGH)}"
                f" | L:{_.get_price(LOW)}"
                f" | C:{_.get_price(CLOSE)}"
                f" | VAH:{_.get_price(VAH)}"
                f" | POC:{_.get_price(POC)}"
                f" | VAL:{_.get_price(VAL)}"
                f" | TIME:{_.get_time(lidx, strftime=True)}",
            )
            self.send_signal(
                nPrice=int(_.to_nPrice(CLOSE)),
                time_ms=(time.time_ns() // 1000 // 1000),
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
