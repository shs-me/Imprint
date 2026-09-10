from dataclasses import dataclass
from multiprocessing.synchronize import Event
from typing import override

from imprint._core.pipeline.executing.base import Base


@dataclass(slots=True)
class Live(Base):
    execution_event: Event

    @override
    def child_post_init(self) -> None: ...

    @override
    def alarm_clock(
        self,
        WB_1: memoryview,
        RB_1: memoryview,
        WB_2: memoryview,
        RB_2: memoryview,
    ) -> None:
        """Blocks process on execution_event when ring buffers are drained."""

        if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
            self.execution_event.clear()
            if (WB_1[0] == RB_1[0]) and (WB_2[0] == RB_2[0]):
                self.execution_event.wait(timeout=0.1)

    @override
    def pre_execute_signal_action(self, time_get_signal: int) -> None: ...
    @override
    def preppare_user_data(self, user_data_raw_buf: memoryview) -> None: ...
    @override
    def post_final_action(self) -> None: ...
