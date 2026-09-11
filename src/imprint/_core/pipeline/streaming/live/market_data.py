import asyncio
from dataclasses import dataclass
from multiprocessing.synchronize import Event
from typing import override

from websockets import ClientConnection

from imprint._core.pipeline.streaming.live.base import Base
from imprint._core.settings import StatusCodes as scs


@dataclass(slots=True)
class MarketData(Base):
    engine_event: Event

    @override
    async def on_pre_connect(self) -> None: ...

    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        raw_data: bytes = await ws.recv(decode=False)

        while self.mds.ring_buf.lag_not_is_safe():
            await asyncio.sleep(0.001)

        if len(raw_data) < self.mds.ring_buf.data_size:
            self.mds.ring_buf.set_data(raw_data)
        else:
            return self.manager.set_proc_sc(
                code=scs.BIG_RAW_DATA, wait_main_task=True
            )
        if self.engine_event.is_set() is False:
            self.engine_event.set()
