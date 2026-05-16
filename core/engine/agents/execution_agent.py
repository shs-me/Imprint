from multiprocessing.synchronize import Event

from core import constant as c
from core.engine.agents.rest_agent import RestAgent
from core.engine.agents_utils.execution.matching_engine import MatchingEngine
from core.engine.agents_utils.execution.trade_manager import TradeManager
from core.engine.agents_utils.utils import TradeConverter
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
        self.tradesParsed: memoryview = self.manager.metrics_buf[
            slice(*self.cfgMetrics.tradesParsed)
        ]
        self.trade_par: memoryview[int] = self.manager.metrics_buf[
            self.cfgMetrics.tick_size[0] : self.cfgMetrics.qtyPrecision[1]
        ].cast("q")
        """symbol trading parameters: tick_size, lot_size, pricePrecision, qtyPrecision"""
        self.tick_size, self.lot_size, self.pricePrec, self.qtyPrec = self.trade_par[:]
        self.priceMult: float = (10**self.pricePrec) + 1e-9
        self.qtyMult: float = (10**self.qtyPrec) + 1e-9
        # Footprint
        self.cfgFP = self.manager.cfgFootprint
        self._space_read: memoryview = self.manager.footprint_buf[
            self.cfgFP.space_read : self.cfgFP.space_read + 1
        ]
        # Variable's
        self.rest: RestAgent = RestAgent(
            symbol=self.symbol, backtesting=self.backtesting, cfgBacktesting=self.cfgBT
        )
        self.con: TradeConverter = TradeConverter(
            trade_param=self.trade_par, cfgStrategy=self.cfgST
        )
        self.tm: TradeManager = TradeManager(manager=self.manager, converter=self.con)
        self.me: MatchingEngine = MatchingEngine(
            manager=self.manager, con=self.con, tm=self.tm
        )
        self.con.init_session(
            startBalance=self.rest.get_balance(),
            minOrderSize=self.rest.get_min_order_size_usdt(),
            takerCommission=self.rest.get_commission(is_maker=False),
            makerCommission=self.rest.get_commission(is_maker=True),
        )

        self.pending_orders: list = []

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

                if WB_2[0] != RB_2[0]:
                    self._check_executed_buf()
                if WB_1[0] != RB_1[0]:
                    self._check_execute_buf()

                if self.backtesting and (self._space_read[0] == 1):
                    if WB_1[0] == RB_1[0] and WB_2[0] == RB_2[0]:
                        self.me.execute_limit_orders()
                        self.tm.prepare_trades()
                        self.check_risk_management()
                        self.me.dfmRID[0] = 0
                        self.me.dfm_RRid[0] = 0
                        self._space_read[0] = 0

    def complete(self) -> bool:
        return (
            self.WB_1[0] == self.RB_1[0]
            and self.WB_2[0] == self.RB_2[0]
            and self._space_read[0] == 0
            and self.tradesParsed[0] == 1
        )

    def final_actions(self) -> None:
        print(
            self.con.nBalance / self.con.scale,
            self.con.lockedNbalance / self.con.scale,
            len(self.tm.openPositions),
            len(self.tm.closePositions),
            self.con.lastOrderId,
            len(self.pending_orders),
        )
        # pprint.pp(self.tm.orders_history[: self.tm.ohWRow[0] :])
        self.set_proc_sc(scs.COMPLETE)

    def _alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        if (WB_1[0] == RB_1[0] and WB_2[0] == RB_2[0]) and self._space_read[0] == 0:
            self.execution_event.clear()
            if (WB_1[0] == RB_1[0] and WB_2[0] == RB_2[0]) and self._space_read[0] == 0:
                self.execution_event.wait(timeout=60)

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
        _, buf, rid = self.con, self.executeBuf, self.readerId
        # - - -
        cell: int = buf[rid]
        start: int = cell * self.signal_size + self.offset

        nPrice: int = _.to_nPrice(_.to_fpPrice(buf[start + self.nPriceId]))
        timestamp: int = buf[start + self.time_msId] + _.latencyMs
        orderParam: int = buf[start + self.orderParamId]

        new_cell: int = cell + 1
        buf[rid] = new_cell if new_cell < self.cell_amount else 0

        if not self.check_risk_management():
            return

        is_long, is_buy = bool(orderParam & c.OF_LONG), bool(orderParam & c.OF_BUY)

        if self.backtesting:
            if (temp := self.me.find_market_order_data(timestamp)) is not None:
                fpNprice, row = temp
                self.me.execute_limit_orders(highWrow=row)
                self.tm.prepare_trades()
                if self.check_risk_management():
                    nQty: int = _.entryNqtyWithLeverage(nPrice)
                    self.open_position_sim(fpNprice, nQty, timestamp, is_long, is_buy)

            else:
                self.pending_orders.append([nPrice, timestamp, is_long, is_buy])

        else:
            pass

    def check_risk_management(self) -> bool:
        _ = self.con
        # - - -
        if not (_.lossNbalanceLimit >= _.nBalance):
            if not (_.lockedNbalance >= _.lockedNbalanceLimit):
                if not ((_.leverage * _.entryNominalNqty) <= _.minOrderNsize):
                    return True
                else:
                    self.set_proc_sc(code=scs.QTY_LESS_LIMIT)
            else:
                pass
        else:
            self.set_proc_sc(code=scs.LOSS_MORE_LIMIT)

        return False

    def open_position_sim(
        self, fpNprice: int, nQty: int, timestamp: int, is_long: bool, is_buy: bool
    ) -> None:
        _ = self.con
        # - - -
        entryNprice = self.me.execute_market_order(
            fpNprice, nQty, timestamp, is_long, is_buy
        )
        self.tm.prepare_trades()
        if not self.check_risk_management():
            return

        nPriceTP = _.TPdevNprice(entryNprice, is_long)
        tpOrderParam = 0
        tpOrderParam |= c.OF_LONG if is_long else c.OF_SHORT
        tpOrderParam |= c.OF_SELL if is_long else c.OF_BUY
        tpOrderParam |= c.OF_LIMIT | c.OF_NEW
        self.tm.update_orders_array(
            nPriceTP, nQty, timestamp + 10, tpOrderParam, None, None
        )

        nPriceSL = _.SLdevNprice(entryNprice, is_long)
        slOrderParam = 0
        slOrderParam |= c.OF_LONG if is_long else c.OF_SHORT
        slOrderParam |= c.OF_SELL if is_long else c.OF_BUY
        slOrderParam |= c.OF_MARKET_TRIGER | c.OF_NEW
        self.tm.update_orders_array(
            nPriceSL, nQty, timestamp + 10, slOrderParam, None, None
        )

        self.tm.prepare_trades()


@manager_office()
def run_execution(execution_event: Event, **kwargs):
    agent = ExecutionAgent(manager=kwargs["manager"], execution_event=execution_event)
    agent.run_execution_engine()
