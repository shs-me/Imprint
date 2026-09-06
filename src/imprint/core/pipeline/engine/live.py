import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import override

from imprint.core.footprint import SyncWithExecution
from imprint.core.pipeline.engine.base import Base
from imprint.core.pipeline.utils.base_adapters import AggTradesDecoder
from imprint.core.settings import StatusCodes as scs


@dataclass(slots=True)
class SyncViaEvent(SyncWithExecution):
    execution_event: Event

    @override
    def sync_with_execution(self) -> None:
        if self.execution_event.is_set() is False:
            self.execution_event.set()


@dataclass(slots=True)
class Live(Base):
    engine_event: Event

    decoder: AggTradesDecoder = field(init=False)
    pass_lag: int = field(default=0, init=False)
    pass_lag_limit: int = field(default=2, init=False)

    def __post_init__(self) -> None:
        Base.__post_init__(self)

        m_name: str = self.manager.cfgSetup.agg_trades_decoder_module
        c_name: str = self.manager.cfgSetup.agg_trades_decoder_class_name
        decoder_type: type[AggTradesDecoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.manager.set_text(
            f"{decoder_type.__name__} used as {AggTradesDecoder.__name__}"
        )
        self.decoder = decoder_type()

    @override
    def alarm_clock(self) -> None:
        self.engine_event.wait(0.1)

    @override
    def set_trade_data(self, raw_data: memoryview) -> None:
        for p, q, t, m in self.decoder.decode(raw_data[:]):
            self.agg_trades[self.at_wid, 0] = round(
                p * self.algorithm._engine.fp.con.price_mult
            )
            self.agg_trades[self.at_wid, 1] = round(
                q * self.algorithm._engine.fp.con.qty_mult
            )
            self.agg_trades[self.at_wid, 2] = t
            self.agg_trades[self.at_wid, 3] = m
            self.at_wid: int = (
                self.at_wid + 1 if (self.at_wid + 1) < self.at_max_row else 0
            )

    @override
    def post_update(self) -> None:
        if self.algorithm._sync.lag_is_safe() is False:
            self.pass_lag += 1
            if self.pass_lag >= self.pass_lag_limit:
                self.manager.set_proc_sc(
                    scs.ANALYSIS_LAG_MORE_SAFE_LAG, wait_main_task=False
                )

        if self.engine_event.is_set():
            self.engine_event.clear()

    @override
    def post_final_action(self) -> None:
        self.algorithm._sync.sync_with_execution()
