"""Live JSON tick payload parser worker."""

import importlib
import inspect
from multiprocessing.synchronize import Event

from msgspec.json import Decoder

from ....settings import ParsingProc
from ....utils.handlers import supervisor
from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_footprint_writer import BaseFootprintWriter, FootprintWriter
from ...base.base_parsing import Parsing
from .data_structs import AggTrades, BinanceAggTrades


class ParsingAgent(Parsing):
    """Parsing process deserializing JSON aggTrade payloads via msgspec."""

    def __init__(
        self,
        manager: AgentManager,
        writer: FootprintWriter,
        aggTrade: type[AggTrades],
        parsing_event: Event,
        logic_event: Event,
    ) -> None:
        super().__init__(manager=manager, writer=writer)

        self.parsing_event: Event = parsing_event
        self.logic_event: Event = logic_event
        self.decoder: Decoder[AggTrades] = Decoder(type=aggTrade, strict=False)

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

        print(f"Count Prepped Ticks: {self.writer.counterTicks[0]}", flush=True)


def resolve_agg_trades_data_struct(manager: AgentManager) -> type[AggTrades]:
    module = importlib.import_module(manager.cfgSetup.agg_trades_struct_module)
    aggTrade: type[AggTrades] = BinanceAggTrades
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if (name == manager.cfgSetup.agg_trades_struct_class_name) and issubclass(
            obj, AggTrades
        ):
            aggTrade = obj

    return aggTrade


@supervisor()
def run_parsing(
    parsing_event: Event,
    logic_event: Event,
    proc: ParsingProc = ParsingProc(),
    **kwargs,
) -> None:
    """Supervisor-wrapped entry point for live Parsing process."""

    writer = BaseFootprintWriter(kwargs["manager"])
    aggTrade = resolve_agg_trades_data_struct(kwargs["manager"])
    agent = ParsingAgent(
        kwargs["manager"], writer, aggTrade, parsing_event, logic_event
    )
    agent.run_parsing_engine()
