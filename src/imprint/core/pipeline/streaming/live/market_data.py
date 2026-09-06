from dataclasses import dataclass
from multiprocessing.synchronize import Event
from typing import override

from websockets import ClientConnection

from imprint.core.pipeline.streaming.live.base import Base


@dataclass(slots=True)
class MarketData(Base):
    engine_event: Event

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        raw_data: bytes = await ws.recv(decode=False)

        await self.alarm_clock(
            self.ds_wid, self.ds_rid, self.ds_cell_amount, self.ds_safe_lag
        )

        if (
            self.set_raw_data(
                raw_data=raw_data,
                writer_id=self.ds_wid,
                data=self.ds_data,
                data_header=self.ds_data_header,
                data_size=self.ds_data_size,
                cell_amount=self.ds_cell_amount,
            )
            and self.engine_event.is_set() is False
        ):
            self.engine_event.set()
