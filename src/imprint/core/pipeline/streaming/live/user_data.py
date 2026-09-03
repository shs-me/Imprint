import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import override

from websockets import ClientConnection

from ...utils.base_adapters import UserStreamDecoder
from .base import Base


@dataclass(slots=True)
class UserData(Base):
    execution_event: Event

    decoder: UserStreamDecoder = field(init=False)

    def __post_init__(self) -> None:
        Base.__post_init__(self)

        m_name: str = self.manager.cfgSetup.user_stream_decoder_module
        c_name: str = self.manager.cfgSetup.user_stream_decoder_class_name
        decoder_type: type[UserStreamDecoder] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.manager.set_text(
            f"{decoder_type.__name__} used as {UserStreamDecoder.__name__}"
        )
        self.decoder = decoder_type(
            price_mult=self.manager.cfgCoin.price_mult,
            qty_mult=self.manager.cfgCoin.qty_mult,
            scale_mult=self.manager.cfgAccount.scale_mult,
        )

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
