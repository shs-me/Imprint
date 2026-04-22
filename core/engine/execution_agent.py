import gc
from multiprocessing.synchronize import Event

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from core.settings import OrderFlag as of

from .. import AgentManager, error_handler, manager_office
from .. import StatusCodes as sc


class ExecutionAgent:
    def __init__(self, execution_event: Event, manager: AgentManager) -> None:
        self.manager, self.execution_event = manager, execution_event
        self.have_task = self.manager.have_task
        self.set_status, self.have_problem = manager.set_status, manager.have_problem
        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""
        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult: float = (10**self.pricePrec) + 1e-9
        self.qtyMult: float = 10**self.qtyPrec + 1e-9
        # Strategy
        self.cfgST = self.manager.cfgStrategy
        self.TP = self.cfgST.TP
        self.SL = self.cfgST.SL
        # TradesArray
        self.lines = self.cfgST.max_trades
        self.cols = self.cfgST.tradeParam
        self._init_array()
        # L/S bufSetup
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
        self.WLB: memoryview[int] = self.longBuf[self.writerId : self.writerId + 1]
        self.RLB: memoryview[int] = self.longBuf[self.readerId : self.readerId + 1]
        self.WSB: memoryview[int] = self.shortBuf[self.writerId : self.writerId + 1]
        self.RSB: memoryview[int] = self.shortBuf[self.readerId : self.readerId + 1]

    def _init_array(self):
        self.trades: NDArray[int64] = np.ndarray(
            shape=(self.lines, self.cols),
            dtype=int64,
            buffer=self.manager.strategy_buf[slice(*self.cfgST.trades)],
        )

    @error_handler(set_status_code=True)
    def run_execution_engine(self) -> None:
        # LocalLinks
        SLEEP, WAKE_UP = sc.SLEEP, sc.WAKE_UP
        set_status, have_problem = self.set_status, self.have_problem
        have_task = self.have_task
        check_signal_buf = self._check_signal_buf
        alarm_clock = self._alarm_clock
        # - - -
        while True:
            gc.collect()
            while True:
                set_status(code=SLEEP)
                if have_problem() is False:
                    if have_task():
                        break

                    alarm_clock()
                    set_status(code=WAKE_UP)
                    check_signal_buf()

                else:
                    return

    def _alarm_clock(self):
        if self.WLB[0] == self.RLB[0] and self.WSB[0] == self.RSB[0]:
            self.execution_event.clear()
            self.execution_event.wait()

    def _check_signal_buf(self) -> None:
        WLB, RLB, WSB, RSB = self.WLB, self.RLB, self.WSB, self.RSB
        # - - -
        while WLB[0] != RLB[0] or WSB[0] != RSB[0]:
            if WLB[0] != RLB[0]:
                self._check_long_buf()
            if WSB[0] != RSB[0]:
                self._check_short_buf()
            pass

    def _check_long_buf(self) -> None:
        nPrice, time_ms, orderParam = self._get_signal(signal_buf=self.longBuf)
        side = orderParam & (of.BUY | of.SELL)
        orderType = orderParam & (of.MARKET | of.LIMIT)
        if side & of.BUY:  # Open Position
            # - - -
            print(f"Open Long: entryPrice:{nPrice} | quantity: 0 | side: BUY")
        elif side & of.SELL:  # Close Position
            # - - -
            print(f"Close Long: entryPrice:{nPrice} | quantity: 0 | side: SELL")

    def _check_short_buf(self) -> None:
        nPrice, time_ms, orderParam = self._get_signal(signal_buf=self.shortBuf)
        side = orderParam & (of.BUY | of.SELL)
        orderType = orderParam & (of.MARKET | of.LIMIT)
        if side & of.SELL:  # Open Position
            # - - -
            print(f"Open Short: entryPrice:{nPrice} | quantity: 0 | side: SELL")
        elif side & of.BUY:  # Close Position
            # - - -
            print(f"Close Short: entryPrice:{nPrice} | quantity: 0 | side: BUY")

    def _get_signal(self, signal_buf: memoryview) -> tuple[int, int, int]:
        cell: int = signal_buf[self.readerId]
        start: int = cell * self.signal_size + self.signal_offset

        nPrice = signal_buf[start + self.nPriceId]
        time_ms = signal_buf[start + self.time_msId]
        orderParam = signal_buf[start + self.orderParamId]

        new_cell = cell + 1
        signal_buf[self.readerId] = new_cell if new_cell < self.cell_amount else 0
        return nPrice, time_ms, orderParam

    def _send_order(self):
        pass

    def set_data_to_trade_array(self, price):
        pass


@manager_office()
def run_execution(execution_event: Event, **kwargs):
    agent = ExecutionAgent(execution_event=execution_event, manager=kwargs["manager"])
    agent.run_execution_engine()
