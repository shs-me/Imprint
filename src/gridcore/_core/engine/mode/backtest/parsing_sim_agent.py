import struct
import time

from ....utils.monitoring.agent_manager import AgentManager
from ....utils.monitoring.office import manager_office
from ...base.base_footprint_writer import FootprintWriter
from ...base.base_parsing import Parsing


class ParsingAgent(Parsing):
    def __init__(self, manager: AgentManager, writer: FootprintWriter) -> None:
        super().__init__(manager=manager, writer=writer)

    def alarm_clock(self) -> None:
        while self.wCellC[0] == self.rCellC[0]:
            time.sleep(0)

    def set_trade_data(self, raw_data: memoryview) -> None:
        self.price[0], self.qty[0], self.timestamp[0], self.is_sell = struct.unpack(
            "@ddq?", raw_data
        )

    def update_success(self) -> None:
        return super().update_success()

    def post_update(self) -> None:
        return super().post_update()

    def post_final_action(self) -> None:
        print(f"Count Prepped Ticks: {self.writer.counterTicks[0]}", flush=True)


@manager_office()
def run_parsing_sim(**kwargs) -> None:
    writer = FootprintWriter(kwargs["manager"])
    agent = ParsingAgent(kwargs["manager"], writer=writer)
    agent.run_parsing_engine()
