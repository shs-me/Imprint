from multiprocessing.synchronize import Event

from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ...base.base_footprint_writer import (
    BaseFootprintWriter,
    FootprintWriter,
)
from ...base.base_parsing import Parsing


class ParsingAgent(Parsing):
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

    def alarm_clock(self) -> None:
        if self.rCellC[0] == self.wCellC[0]:
            self.parsing_event.wait()

    def set_trade_data(self, raw_data: memoryview) -> None:
        trade = self.decoder.decode(raw_data[:])
        self.price[0], self.qty[0], self.timestamp[0] = trade.p, trade.q, trade.T
        self.is_sell = trade.m

    def update_success(self) -> None:
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


@manager_office()
def run_parsing(parsing_event: Event, logic_event: Event, **kwargs) -> None:
    writer = BaseFootprintWriter(kwargs["manager"])
    agent = ParsingAgent(kwargs["manager"], writer, logic_event, parsing_event)
    agent.run_parsing_engine()
