from multiprocessing.synchronize import Event
from typing import final, override

from msgspec.json import Decoder

from ...footprint.engine import FootprintEngine, SyncWithExecution
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ..utils.structs import create_aggtrades_struct
from .base import Base


class SyncViaEvent(SyncWithExecution):
    def __init__(self, manager: NodeManager, execution_event: Event) -> None:
        super().__init__(manager)

        self.execution_event: Event = execution_event

    @override
    def sync_with_execution(self) -> None:
        if self.execution_event.is_set() is False:
            self.execution_event.set()


class Live(Base):
    nPrice: int
    nQty: int
    timestamp: int
    is_sell: int

    def __init__(
        self, manager: NodeManager, engine: FootprintEngine, engine_event: Event
    ) -> None:
        super().__init__(manager, engine)

        self.engine_event: Event = engine_event

        fields_names = manager.cfgSetup.agg_trades_struct_fields_names
        agg_trades_type = create_aggtrades_struct(fields_names)
        self.decoder = Decoder(type=agg_trades_type, strict=False)
        self.pass_lag: int = 0
        self.pass_lag_limit: int = 2

    @override
    def alarm_clock(self) -> None:
        self.engine_event.wait(0.1)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        trade = self.decoder.decode(raw_data[:])
        self.nPrice = round(trade.price * self.engine.con.price_mult)
        self.nQty = round(trade.qty * self.engine.con.qty_mult)
        self.timestamp = trade.timestamp
        self.is_sell = int(trade.is_sell)

    @override
    def post_update(self) -> None:
        if self.engine._sync.lag_is_safe() is False:
            self.pass_lag += 1
            if self.pass_lag >= self.pass_lag_limit:
                self.manager.set_proc_sc(
                    scs.ANALYSIS_LAG_MORE_SAFE_LAG, wait_main_task=False
                )

        if self.ds_wid[0] == self.ds_rid[0]:
            if self.engine_event.is_set():
                self.engine_event.clear()

    @override
    def post_final_action(self) -> None:
        self.engine._sync.sync_with_execution()
