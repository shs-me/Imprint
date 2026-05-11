from multiprocessing.synchronize import Event

from core.engine.agents.rest_agent import RestAgent
from core.engine.agents_utils.execution.trade_manager import TradeManager
from core.engine.agents_utils.utils import TradeConverter
from core.settings import OrderFlag
from core.utils.handlers import error_handler
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.office import manager_office
from core.utils.monitoring.status_codes import StatusCodes as scs


class ExecutionAgent:
    def __init__(
        self,
        manager: AgentManager,
        execution_event: Event,
    ) -> None:
        self.manager: AgentManager = manager
        self.execution_event: Event = execution_event

        # AgentManager
        self.symbol: str = self.manager.symbol
        self.backtesting = self.manager.backtesting
        self.set_proc_sc = self.manager.set_proc_sc
        self.check_base_task = self.manager.check_base_task
        self.task_status: memoryview = self.manager.task_status
        self.proc_status: memoryview = self.manager.proc_status

        # Backtesting
        self.cfgBT = self.manager.cfgBacktesting
        # Strategy
        self.cfgST = self.manager.cfgStrategy
        self.cell_amount: int = self.cfgST.cell_amount
        self.readerId: int = self.cfgST.reader[1] // 8 - 1
        self.writerId: int = self.cfgST.writer[1] // 8 - 1
        self.offset: int = self.cfgST.offset // 8
        self.nPriceId: int = self.cfgST.nPrice[1] // 8 - 1
        self.time_msId: int = self.cfgST.time_ms[1] // 8 - 1
        self.orderParamId: int = self.cfgST.orderParam[1] // 8 - 1
        self.orderIdId: int = self.cfgST.orderID[1] // 8 - 1
        self.commissionId: int = self.cfgST.commission[1] // 8 - 1

        self.signal_size: int = self.cfgST.signal_size // 8
        self.executeBuf: memoryview = self.manager.strategy_buf[
            slice(*self.cfgST.executeBuf)
        ].cast("q")
        self.WB_1: memoryview[int] = self.executeBuf[self.writerId : self.writerId + 1]
        self.RB_1: memoryview[int] = self.executeBuf[self.readerId : self.readerId + 1]

        self.executed_size: int = self.cfgST.executed_size // 8
        self.executedBuf: memoryview = self.manager.strategy_buf[
            slice(*self.cfgST.executedBuf)
        ].cast("q")
        self.WB_2: memoryview[int] = self.executedBuf[self.writerId : self.writerId + 1]
        self.RB_2: memoryview[int] = self.executedBuf[self.readerId : self.readerId + 1]

        # Metrics
        self.cfgMetrics = self.manager.cfgMetrics
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""
        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult: float = (10**self.pricePrec) + 1e-9
        self.qtyMult: float = 10**self.qtyPrec + 1e-9

        # Variable's
        self.con = TradeConverter(trade_param=self.trade_par, cfgStrategy=self.cfgST)
        self.trade_manager = TradeManager(manager=self.manager, converter=self.con)
        self.rest: RestAgent = RestAgent(
            symbol=self.symbol, backtesting=self.backtesting, cfgBacktesting=self.cfgBT
        )

        self.minOrderNsize: int = round(
            self.rest.get_min_order_size_usdt() * self.con.scale
        )
        self.startNbalance: int = round(self.rest.get_balance() * self.con.scale)
        self.nBalance: int = self.startNbalance
        self.lockedNbalance: int = 0
        self.maxLockNbalance: int = self.cfgST.maxLockBalance
        self.maxLossNbalance: int = (
            self.startNbalance * self.cfgST.maxLossBalance // 1000
        )

        self.TProi = self.cfgST.TProi
        self.SLroi = self.cfgST.SLroi

    @error_handler(set_status_code=True)
    def run_execution_engine(self) -> None:
        # LocalLinks
        proc_status, task_status = self.proc_status, self.task_status
        # - - -
        WB_1, RB_1, WB_2, RB_2 = self.WB_1, self.RB_1, self.WB_2, self.RB_2
        # - - -
        alarm_clock = self._alarm_clock
        # - - -
        while True:
            # - - -
            while True:
                if proc_status[0] != 0 or task_status[0] != 0:
                    task: bool | int = self.check_base_task(complete=self.complete())
                    if isinstance(task, bool):
                        if task:
                            if task_status[0] & scs.COMPLETE:
                                self.final_actions()
                            return

                alarm_clock(WB_1, RB_1, WB_2, RB_2)

                while WB_1[0] != RB_1[0] or WB_2[0] != RB_2[0]:
                    if WB_2[0] != RB_2[0]:
                        self._check_executed_buf()
                    if WB_1[0] != RB_1[0]:
                        self._check_execute_buf()

    def complete(self) -> bool:
        return self.WB_1[0] == self.RB_1[0] and self.WB_2[0] == self.RB_2[0]

    def final_actions(self) -> None:
        self.set_proc_sc(scs.COMPLETE)

    def _alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        if WB_1[0] == RB_1[0] and WB_2[0] == RB_2[0]:
            self.execution_event.clear()
            if WB_1[0] == RB_1[0] and WB_2[0] == RB_2[0]:
                self.execution_event.wait()

    def _check_executed_buf(self) -> None:
        cell: int = self.executedBuf[self.readerId]
        start: int = cell * self.executed_size + self.offset

        _nPrice = self.executedBuf[start + self.nPriceId]
        _time_ms = self.executedBuf[start + self.time_msId]
        _orderParam = self.executedBuf[start + self.orderParamId]
        _orderID = self.executedBuf[start + self.orderIdId]
        _commission = self.executedBuf[start + self.commissionId]

        new_cell = cell + 1
        self.executedBuf[self.readerId] = new_cell if new_cell < self.cell_amount else 0
        #  - - -

    def _check_execute_buf(self) -> None:
        cell: int = self.executeBuf[self.readerId]
        start: int = cell * self.signal_size + self.offset

        _nPrice = self.executeBuf[start + self.nPriceId]
        _time_ms = self.executeBuf[start + self.time_msId]
        orderParam = self.executeBuf[start + self.orderParamId]

        new_cell = cell + 1
        self.executeBuf[self.readerId] = new_cell if new_cell < self.cell_amount else 0
        #  - - -
        if self.maxLossNbalance >= self.nBalance:
            self.set_proc_sc(code=scs.LOSS_MORE_LIMIT)
            return

        if self.lockedNbalance >= (self.nBalance * self.maxLockNbalance // 1000):
            return

        nPrice: int = self.con.to_nPrice(self.con.to_fpPrice(_nPrice))
        nQty: int = self.con.get_nQty(nPrice, self.nBalance - self.lockedNbalance)

        if (nPrice * nQty // self.con.scale) <= self.minOrderNsize:
            self.set_proc_sc(code=scs.QTY_LESS_LIMIT)
            return

        nPriceTP = nPrice * (1 + self.TProi) // 1000
        nPriceSL = nPrice * (1 + self.SLroi) // 1000

        self.rest.send_new_batchOrder(
            price=self.con.to_price(nPrice),
            qty=self.con.to_qty(nQty),
            tpPrice=self.con.to_price(nPriceTP),
            slPrice=self.con.to_price(nPriceSL),
            is_long=bool(orderParam & OrderFlag.LONG),
            is_buy=bool(orderParam & OrderFlag.BUY),
            is_market=True,
        )
        # - - -


@manager_office()
def run_execution(execution_event: Event, **kwargs):
    agent = ExecutionAgent(manager=kwargs["manager"], execution_event=execution_event)
    agent.run_execution_engine()
