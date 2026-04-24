import gc
from multiprocessing.synchronize import Event

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from core.engine.network.rest_engine import RestEngine
from core.engine.network_sim.rest_sim_engine import RestSimAgent
from core.settings import OrderFlag as of
from core.utils.handlers import error_handler
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office
from core.utils.monitoring.status_codes import StatusCodes as scs


class ExecutionAgent:
    def __init__(
        self,
        manager: AgentManager,
        rest: RestEngine | RestSimAgent,
        execution_event: Event,
    ) -> None:
        self.manager: AgentManager = manager
        self.rest: RestEngine | RestSimAgent = rest
        self.execution_event: Event = execution_event

        self.set_proc_sc = manager.set_proc_sc
        self.check_task = manager.check_task
        self.task_status: memoryview = manager.task_status
        self.proc_status: memoryview = manager.proc_status

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
        proc_status, task_status = self.proc_status, self.task_status
        # - - -
        check_signal_buf = self._check_signal_buf
        alarm_clock = self._alarm_clock
        # - - -
        while True:
            while True:
                if proc_status[0] != 0 or task_status[0] != 0:
                    if task := self.check_task(
                        complete=(
                            self.WLB[0] == self.RLB[0] and self.WSB[0] == self.RSB[0]
                        )
                    ):
                        return

                    elif task is False:
                        pass

                alarm_clock()
                check_signal_buf()

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
    type_rest = RestSimAgent if kwargs["backtesting"] else RestEngine
    rest = type_rest(manager=kwargs["manager"])
    agent = ExecutionAgent(
        manager=kwargs["manager"], rest=rest, execution_event=execution_event
    )
    agent.run_execution_engine()
