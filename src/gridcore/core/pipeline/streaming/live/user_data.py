import importlib
from multiprocessing.synchronize import Event
from typing import override

from websockets import ClientConnection

from ....ipc import NodeManager
from ...utils.base_adapters import UserStreamDecoder
from ...utils.rest_agent import RestAgent
from .base import Base


class UserData(Base):
    def __init__(self, manager: NodeManager, execution_event: Event) -> None:
        self.execution_event: Event = execution_event

        m_name: str = manager.cfgSetup.user_stream_decoder_module
        c_name: str = manager.cfgSetup.user_stream_decoder_class_name
        decoder_type: type[UserStreamDecoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.decoder: UserStreamDecoder = decoder_type()
        self.rest: RestAgent = RestAgent(
            symbol=self.manager.cfgCoin.symbol, connector=manager.cfgConnector
        )
        self.user_data_uri: str = manager.cfgConnector.get_user_data_uri_for_wss

        super().__init__(manager, self.user_data_uri)

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
