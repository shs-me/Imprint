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

        cfgAC = manager.cfgAccount
        self.analysis_safe_lag_us: int = cfgAC.analysis_safe_lag_microsecond

        cfgSN = manager.cfgSignal
        self.sn_cell_amount: int = cfgSN.cell_amount
        self.sn_data_size: int = cfgSN.data_size
        self.sn_data: memoryview = cfgSN.data
        self.WB_1: memoryview = cfgSN.writer_id.cast("q")
        self.RB_1: memoryview = cfgSN.reader_id.cast("q")

        cfgUS = manager.cfgUserStream
        self.us_cell_amount: int = cfgUS.cell_amount
        self.us_data_size: int = cfgUS.data_size
        self.us_data: memoryview = cfgUS.data
        self.WB_2: memoryview = cfgUS.writer_id.cast("q")
        self.RB_2: memoryview = cfgUS.reader_id.cast("q")

        cfgMetrics = manager.cfgMetrics
        self.logic_complete: memoryview = cfgMetrics.logic_complete
        self.con: TradeConverter = TradeConverter(
            cfgAcount=cfgAC,
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
        pass

    @abstractmethod
    def pre_executed_actions(self) -> None:
        pass

    @abstractmethod
    def executed_action(self) -> None:
        pass

    def check_execute_buf(self) -> None:
        _ = self.con
        # - - -
        cell: int = self.RB_1[0]
        start: int = cell * self.sn_data_size
        get_data: memoryview = self.sn_data[start : start + self.sn_data_size].cast("q")
        nPrice, timestamp, order_param = get_data[0], get_data[1], get_data[2]
        new_cell: int = cell + 1
        self.RB_1[0] = new_cell if (new_cell < self.sn_cell_amount) else 0

        self.pre_execute_actions()
        if _.lossNbalanceSafeLimit:
            if _.lockedNbalanceSafeLimit:
                if _.nominalEntryNqtyWithLeverage is not None:
                    self.execute_action(nPrice, timestamp, order_param)
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
