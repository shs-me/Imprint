from abc import ABC, abstractmethod

from ...utils.handlers import error_handler
from ...utils.monitoring.agent_manager import AgentManager
from ...utils.monitoring.status_codes import StatusCodes as scs
from .utils.tm_con import TradeConverter


class Execution(ABC):
    def __init__(self, manager: AgentManager) -> None:
        self.manager: AgentManager = manager

        self.symbol: str = manager.symbol
        self.set_proc_sc = manager.set_proc_sc
        self.check_base_task = manager.check_base_task
        self.task_status, self.proc_status = manager.task_status, manager.proc_status

        cfgST = manager.cfgStrategy
        self.cell_amount: int = cfgST.cell_amount
        self.readerId: int = cfgST.reader[1] // 8 - 1
        self.writerId: int = cfgST.writer[1] // 8 - 1
        self.offset: int = cfgST.offset // 8
        self.nPriceId: int = cfgST.nPrice[1] // 8 - 1
        self.time_msId: int = cfgST.time_ms[1] // 8 - 1
        self.orderParamId: int = cfgST.orderParam[1] // 8 - 1
        self.orderIdId: int = cfgST.orderID[1] // 8 - 1
        self.commissionId: int = cfgST.commission[1] // 8 - 1
        self.signal_size: int = cfgST.signal_size // 8
        self.executeBuf = manager.strategy_buf[slice(*cfgST.executeBuf)].cast("q")
        self.WB_1: memoryview = self.executeBuf[self.writerId : self.writerId + 1]
        self.RB_1: memoryview = self.executeBuf[self.readerId : self.readerId + 1]
        self.executed_size: int = cfgST.executed_size // 8
        self.executedBuf = manager.strategy_buf[slice(*cfgST.executedBuf)].cast("q")
        self.WB_2: memoryview = self.executedBuf[self.writerId : self.writerId + 1]
        self.RB_2: memoryview = self.executedBuf[self.readerId : self.readerId + 1]

        cfgMetrics = manager.cfgMetrics
        self.logic_complete: memoryview = cfgMetrics.logic_complete
        self.con: TradeConverter = TradeConverter(
            cfgST=cfgST,
            price_prec=cfgMetrics.price_precision.cast("q"),
            qty_prec=cfgMetrics.qty_precision.cast("q"),
        )

    @error_handler(set_status_code=True)
    def run_execution_engine(self) -> None:
        # LocalLinks
        proc_status, task_status = self.proc_status, self.task_status
        WB_1, RB_1, WB_2, RB_2 = self.WB_1, self.RB_1, self.WB_2, self.RB_2
        alarm_clock = self.alarm_clock
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
                    self.check_executed_buf()
                if WB_1[0] != RB_1[0]:
                    self.check_execute_buf()

                self.post_check_bufs(WB_1, RB_1, WB_2, RB_2)

    def complete(self) -> bool:
        return (self.logic_complete[0] == 1) and (
            (self.WB_1[0] == self.RB_1[0]) and (self.WB_2[0] == self.RB_2[0])
        )

    def final_actions(self) -> None:
        self.post_final_action()
        self.set_proc_sc(scs.COMPLETE)

    def post_final_action(self) -> None:
        pass

    @abstractmethod
    def alarm_clock(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        pass

    @abstractmethod
    def post_check_bufs(
        self, WB_1: memoryview, RB_1: memoryview, WB_2: memoryview, RB_2: memoryview
    ) -> None:
        pass

    def check_executed_buf(self) -> None:
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
        self.pre_executed_actions()
        self.executed_action()

    @abstractmethod
    def pre_executed_actions(self) -> None:
        pass

    @abstractmethod
    def executed_action(self) -> None:
        pass

    def check_execute_buf(self) -> None:
        _, buf, rid = self.con, self.executeBuf, self.readerId
        # - - -
        cell: int = buf[rid]
        start: int = cell * self.signal_size + self.offset

        nPrice: int = _.to_nPrice(buf[start + self.nPriceId])
        timestamp: int = buf[start + self.time_msId]
        orderParam: int = buf[start + self.orderParamId]

        new_cell: int = cell + 1
        buf[rid] = new_cell if (new_cell < self.cell_amount) else 0

        self.pre_execute_actions()
        if _.lossNbalanceSafeLimit:
            if _.lockedNbalanceSafeLimit:
                if _.nominalEntryNqtyWithLeverage is not None:
                    self.execute_action(nPrice, timestamp, orderParam)
                else:
                    self.set_proc_sc(code=scs.QTY_LESS_LIMIT)
            else:
                pass
        else:
            self.set_proc_sc(code=scs.LOSS_MORE_LIMIT)

    @abstractmethod
    def pre_execute_actions(self) -> None:
        pass

    @abstractmethod
    def execute_action(
        self, nPrice: int, time_get_signal: int, orderParam: int
    ) -> None:
        pass
