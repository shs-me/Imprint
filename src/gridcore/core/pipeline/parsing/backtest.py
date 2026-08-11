import struct
import time

from ...footprint import BaseFootprintWriter
from ...ipc import NodeManager
from .base import Base


class Backtest(Base):
    def __init__(self, manager: NodeManager, writer: BaseFootprintWriter) -> None:
        super().__init__(manager=manager, writer=writer)

    def alarm_clock(self) -> None:
        time.sleep(0)

    def set_trade_data(self, raw_data: memoryview) -> None:
        self.price[0], self.qty[0], self.timestamp[0], self.is_sell = struct.unpack(
            "@ddq?", raw_data
        )

    def update_success(self) -> None:
        return super().update_success()

    def post_update(self) -> None:
        return super().post_update()

    def final_actions(self) -> None:
        self.manager.set_text(f"Count Prepped Ticks: {self.writer.counter_ticks[0]}")

    def post_final_action(self) -> None:
        pass
