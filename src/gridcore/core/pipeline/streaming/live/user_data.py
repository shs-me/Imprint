import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import override

from websockets import ClientConnection

from ....ipc import NodeManager
from ...utils.base_adapters import UserStreamDecoder
from .base import Base


@dataclass(slots=True, init=False)
class UserData(Base):
    execution_event: Event

    decoder: UserStreamDecoder = field(init=False)
    uri: str = field(init=False)

    def __init__(self, manager: NodeManager, execution_event: Event) -> None:
        self.execution_event = execution_event

        m_name: str = manager.cfgSetup.user_stream_decoder_module
        c_name: str = manager.cfgSetup.user_stream_decoder_class_name
        decoder_type: type[UserStreamDecoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.decoder = decoder_type(
            price_mult=manager.cfgCoin.price_mult,
            qty_mult=manager.cfgCoin.qty_mult,
            scale_mult=manager.cfgAccount.scale_mult,
        )
        self.uri = manager.cfgConnector.get_user_data_uri_for_wss

        super().__init__(manager, self.uri)

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        raw_data: bytes = await ws.recv(decode=False)

        await self.alarm_clock(
            self.gus_wid, self.gus_rid, self.gus_cell_amount, self.gus_safe_lag
        )

        if self.set_raw_data(
            raw_data=raw_data,
            writer_id=self.gus_wid,
            data=self.gus_data,
            data_header=self.gus_data_header,
            data_size=self.gus_data_size,
            cell_amount=self.gus_cell_amount,
        ):
            if self.execution_event.is_set() is False:
                self.execution_event.set()
