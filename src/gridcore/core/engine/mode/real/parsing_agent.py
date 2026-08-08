"""Live JSON tick payload parser worker."""

import importlib
from multiprocessing.synchronize import Event

from msgspec.json import Decoder

from ....settings import ParsingProc
from ....utils.handlers import supervisor
from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_footprint_writer import FootprintWriter
from ...base.base_parsing import Parsing
from .base_adapters import AggTrades


class ParsingAgent(Parsing):
    """Parsing process deserializing JSON aggTrade payloads via msgspec."""

    def __init__(
        self,
        manager: AgentManager,
        writer: FootprintWriter,
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
        """Blocks process on parsing_event until new WebSocket frame arrives."""

        if self.rCellC[0] == self.wCellC[0]:
            self.parsing_event.wait()

    def set_trade_data(self, raw_data: memoryview) -> None:
        """Decodes raw JSON buffer using msgspec Decoder into tick attributes."""

        trade = self.decoder.decode(raw_data[:])
        self.price[0] = trade.price()
        self.qty[0] = trade.qty()
        self.timestamp[0] = trade.timestamp()
        self.is_sell = trade.is_sell()

    def update_success(self) -> None:
        """Sets logic_event to wake up strategy engine upon Footprint update."""

        if self.logic_event.is_set() is False:
            self.logic_event.set()

    def post_update(self) -> None:
        if self.wCellC[0] == self.rCellC[0]:
            if self.parsing_event.is_set():
                self.parsing_event.clear()

    def post_final_action(self) -> None:
        if self.logic_event.is_set() is False:
            self.logic_event.set()

        print(f"Count Prepped Ticks: {self.writer.counter_ticks[0]}", flush=True)


@supervisor()
def run_parsing(
    parsing_event: Event,
    logic_event: Event,
    proc: ParsingProc = ParsingProc(),
    **kwargs,
) -> None:
    """Supervisor-wrapped entry point for live Parsing process."""

    writer = FootprintWriter(kwargs["manager"])
    agent = ParsingAgent(kwargs["manager"], writer, parsing_event, logic_event)
    agent.run_parsing_engine()
