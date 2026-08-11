import importlib
from multiprocessing.synchronize import Event

from msgspec.json import Decoder

from ...footprint import BaseFootprintWriter
from ...ipc import NodeManager
from ..utils.base_adapters import AggTrades
from .base import Base


class Live(Base):
    def __init__(
        self,
        manager: NodeManager,
        writer: BaseFootprintWriter,
        parsing_event: Event,
        logic_event: Event,
    ) -> None:
        super().__init__(manager=manager, writer=writer)

        self.parsing_event: Event = parsing_event
        self.logic_event: Event = logic_event

        m_name = manager.cfgSetup.agg_trades_struct_module
        c_name = manager.cfgSetup.agg_trades_struct_class_name
        self.agg_trade: type[AggTrades] = getattr(
            importlib.import_module(m_name), c_name
        )
        manager.set_text(
            f"{self.agg_trade.__class__.__name__} used as {AggTrades.__name__}"
        )
        self.decoder: Decoder[AggTrades] = Decoder(type=self.agg_trade, strict=False)

    def alarm_clock(self) -> None:
        if self.ds_wid[0] == self.ds_rid[0]:
            self.parsing_event.wait()

    def set_trade_data(self, raw_data: memoryview) -> None:
        trade = self.decoder.decode(raw_data[:])
        self.price[0] = trade.price()
        self.qty[0] = trade.qty()
        self.timestamp[0] = trade.timestamp()
        self.is_sell = trade.is_sell()

    def update_success(self) -> None:
        if self.logic_event.is_set() is False:
            self.logic_event.set()

    def post_update(self) -> None:
        if self.ds_wid[0] == self.ds_rid[0]:
            if self.parsing_event.is_set():
                self.parsing_event.clear()

    def post_final_action(self) -> None:
        if self.logic_event.is_set() is False:
            self.logic_event.set()

        self.manager.set_text(f"Count Prepped Ticks: {self.writer.counter_ticks[0]}")
