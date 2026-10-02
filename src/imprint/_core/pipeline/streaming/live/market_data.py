import asyncio
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

    gap_task: asyncio.Task[None] | None = field(default=None, init=False)
    sem: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(5), init=False
    )

    @override
    def post_init(self) -> None:
        Base.post_init(self)

        self.have_gap = self.mdgs.have_gap.view
        self.first_gap_id = self.mdgs.gap_first_id.view.cast("q")
        self.last_gap_id = self.mdgs.gap_last_id.view.cast("q")

    @override
    async def on_pre_connect(self) -> None:
        if self.gap_task is None:
            self.gap_task = asyncio.create_task(self.monitor_gap())

    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        _ = self.mds.ring_buf
        # - - -
        raw_data: bytes = await ws.recv(decode=False)

        while _.lag_not_is_safe():
            await asyncio.sleep(0.001)

        if len(raw_data) < _.data_size:
            _.set_data(raw_data)
        else:
            return self.manager.set_proc_sc(
                code=scs.BIG_RAW_DATA, wait_main_task=True
            )

        if not self.engine_event.is_set():
            self.engine_event.set()

    async def monitor_gap(self) -> None:
        try:
            wid, rid = self.mdgs.ring_buf.wid_buf, self.mdgs.ring_buf.rid_buf
            #  - - -
            while True:
                while not self.have_gap[0]:
                    await asyncio.sleep(0.01)

                while wid[0] != rid[0]:
                    await asyncio.sleep(0.01)

                first_id: int = self.first_gap_id[0]
                last_gap_id: int = self.last_gap_id[0]

                if (last_gap_id - first_id) <= 1000:
                    await self.gap_request(first_id, last_gap_id, self.sem)
                else:
                    async with asyncio.TaskGroup() as tg:
                        curr_first = first_id
                        while curr_first < last_gap_id:
                            curr_last = min(curr_first + 1000, last_gap_id)
                            tg.create_task(
                                self.gap_request(
                                    curr_first, curr_last, self.sem
                                )
                            )
                            curr_first = curr_last

                self.have_gap[0] = 0

        except Exception as e:
            self.manager.dump_exc(True)
            self.manager.set_log(f"{self.stream} Gap request failed: {e}")
        finally:
            self.gap_task = None

    async def gap_request(
        self, first_id: int, last_id: int, sem: asyncio.Semaphore
    ) -> None:
        _ = self.mdgs.ring_buf
        # - - -
        async with sem:
            raw_data: bytes = await self.rest.get_agg_trades(first_id, last_id)

        while _.lag_not_is_safe():
            await asyncio.sleep(0.001)

        if len(raw_data) < _.data_size:
            _.set_data(raw_data)
            if not self.engine_event.is_set():
                self.engine_event.set()
        else:
            return self.manager.set_proc_sc(
                code=scs.BIG_RAW_DATA, wait_main_task=True
            )
