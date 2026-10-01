import asyncio
from asyncio.tasks import Task
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import override

from websockets import ClientConnection

from imprint._core.pipeline.streaming.live.base import Base
from imprint._core.settings import StatusCodes as scs


@dataclass(slots=True)
class MarketData(Base):
    engine_event: Event

    have_gap: memoryview = field(init=False)
    first_gap_id: memoryview = field(init=False)
    last_gap_id: memoryview = field(init=False)

    gap_task: Task[None] | None = field(default=None, init=False)

    @override
    def post_init(self) -> None:
        Base.post_init(self)

        self.have_gap = self.mdgs.have_gap.view
        self.first_gap_id = self.mdgs.gap_first_id.view.cast("q")
        self.last_gap_id = self.mdgs.gap_last_id.view.cast("q")

    @override
    async def on_pre_connect(self) -> None: ...

    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        _ = self.mds.ring_buf
        # - - -
        if self.have_gap[0] and (self.gap_task is None):
            self.gap_task = asyncio.create_task(self.safe_gap_request())

        raw_data: bytes = await ws.recv(decode=False)

        while _.lag_not_is_safe():
            await asyncio.sleep(0.001)

        if len(raw_data) < _.data_size:
            _.set_data(raw_data)
        else:
            return self.manager.set_proc_sc(
                code=scs.BIG_RAW_DATA, wait_main_task=True
            )
        if self.engine_event.is_set() is False:
            self.engine_event.set()

    async def safe_gap_request(self) -> None:
        try:
            _ = self.mdgs.ring_buf
            #  - - -
            while _.wid_buf[0] != _.rid_buf[0]:
                await asyncio.sleep(0.001)

            first_id, last_gap_id = self.first_gap_id[0], self.last_gap_id[0]

            if (last_gap_id - first_id) <= 1000:
                await self.gap_request(first_id, last_gap_id)
            else:
                async with asyncio.TaskGroup() as tg:
                    curr_first = first_id
                    while curr_first < last_gap_id:
                        curr_last = min(curr_first + 1000, last_gap_id)
                        tg.create_task(self.gap_request(curr_first, curr_last))
                        curr_first = curr_last

            self.have_gap[0] = 0

        except Exception as e:
            self.manager.dump_exc(True)
            self.manager.set_log(f"{self.stream} Gap request failed: {e}")
        finally:
            self.gap_task = None

    async def gap_request(self, first_id: int, last_id: int) -> None:
        _ = self.mdgs.ring_buf
        # - - -
        raw_data: bytes = await self.rest.get_agg_trades(first_id, last_id)

        while _.lag_not_is_safe():
            await asyncio.sleep(0.001)

        if len(raw_data) < _.data_size:
            _.set_data(raw_data)
        else:
            return self.manager.set_proc_sc(
                code=scs.BIG_RAW_DATA, wait_main_task=True
            )
