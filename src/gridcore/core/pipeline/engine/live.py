import importlib
from multiprocessing.synchronize import Event
from typing import final, override

from ...footprint.engine import FootprintEngine, SyncWithExecution
from ...ipc import NodeManager
from ...settings import StatusCodes as scs
from ..utils.base_adapters import AggTradesDecoder
from .base import Base


@final
class SyncViaEvent(SyncWithExecution):
    def __init__(self, manager: NodeManager, execution_event: Event) -> None:
        super().__init__(manager)

        self.execution_event: Event = execution_event

    @override
    def sync_with_execution(self) -> None:
        if self.execution_event.is_set() is False:
            self.execution_event.set()


class Live(Base):
    at_wid: int

    def __init__(
        self, manager: NodeManager, engine: FootprintEngine, engine_event: Event
    ) -> None:
        super().__init__(manager, engine)

        self.engine_event: Event = engine_event

        m_name: str = manager.cfgSetup.agg_trades_decoder_module
        c_name: str = manager.cfgSetup.agg_trades_decoder_class_name
        decoder_type: type[AggTradesDecoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        manager.set_text(
            f"{decoder_type.__class__.__name__} used as {AggTradesDecoder.__name__}"
        )
        self.decoder: AggTradesDecoder = decoder_type()

        self.pass_lag: int = 0
        self.pass_lag_limit: int = 2

    @override
    def alarm_clock(self) -> None:
        self.engine_event.wait(0.1)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        for p, q, t, m in self.decoder.decode(raw_data[:]):
            self.agg_trades[self.at_wid, 0] = round(p * self.engine.con.price_mult)
            self.agg_trades[self.at_wid, 1] = round(q * self.engine.con.qty_mult)
            self.agg_trades[self.at_wid, 2] = t
            self.agg_trades[self.at_wid, 3] = m
            self.at_wid = self.at_wid + 1 if (self.at_wid + 1) < self.at_max_row else 0

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
