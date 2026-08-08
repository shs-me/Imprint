"""Simulated tick binary parser process."""

import struct
import time

from ....settings import ParsingProc
from ....utils.handlers import supervisor
from ....utils.monitoring.agent_manager import AgentManager
from ...base.base_footprint_writer import FootprintWriter
from ...base.base_parsing import Parsing


class ParsingAgent(Parsing):
    """Parsing process unpacking binary struct payloads into Footprint updates."""

    def __init__(self, manager: AgentManager, writer: FootprintWriter) -> None:
        super().__init__(manager=manager, writer=writer)

    def alarm_clock(self) -> None:
        """Idle wait loop invoked while DataStream ring buffer is empty."""

        while self.wCellC[0] == self.rCellC[0]:
            time.sleep(0)

    def set_trade_data(self, raw_data: memoryview) -> None:
        """Unpacks `@ddq?` binary payload into price, quantity, timestamp, and side attributes."""

        self.price[0], self.qty[0], self.timestamp[0], self.is_sell = struct.unpack(
            "@ddq?", raw_data
        )

    def update_success(self) -> None:
        return super().update_success()

    def post_update(self) -> None:
        return super().post_update()

    def final_actions(self) -> None:
        """Logs total prepped tick count upon process teardown."""

        super().final_actions()
        self.manager.set_text(f"Count Prepped Ticks: {self.writer.counter_ticks[0]}")

    def post_final_action(self) -> None:
        pass


@supervisor()
def run_parsing_sim(proc: ParsingProc = ParsingProc(), **kwargs) -> None:
    """Supervisor-wrapped entry point for simulated Parsing process."""

    writer = FootprintWriter(kwargs["manager"])
    agent = ParsingAgent(kwargs["manager"], writer=writer)
    agent.run_parsing_engine()
