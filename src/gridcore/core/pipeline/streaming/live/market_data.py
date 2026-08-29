from multiprocessing.synchronize import Event
from typing import override

from websockets import ClientConnection

from ....ipc import NodeManager
from .base import Base


class MarketData(Base):
    def __init__(self, manager: NodeManager, engine_event: Event) -> None:
        self.engine_event: Event = engine_event
        self.agg_trades_uri: str = manager.cfgConnector.market_data_uri_for_wss
        super().__init__(manager, self.agg_trades_uri)

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        raw_data: bytes = await ws.recv(decode=False)

        await self.alarm_clock(
            self.ds_wid, self.ds_rid, self.ds_cell_amount, self.ds_safe_lag
        )

        if self.set_raw_data(
            raw_data=raw_data,
            writer_id=self.ds_wid,
            data=self.ds_data,
            data_header=self.ds_data_header,
            data_size=self.ds_data_size,
            cell_amount=self.ds_cell_amount,
        ):
            if self.engine_event.is_set() is False:
                self.engine_event.set()
