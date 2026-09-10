import asyncio
import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import Any, override

from websockets import ClientConnection

from imprint._core.pipeline.streaming.live.base import Base
from imprint._core.settings import StatusCodes as scs
from imprint._core.utils import UserStreamDecoder


@dataclass(slots=True)
class UserData(Base):
    execution_event: Event

    decoder: UserStreamDecoder[Any] = field(init=False)
    base_uri: str = field(init=False)
    keep_task: asyncio.Task[None] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        Base.__post_init__(self)

        m_name: str = self.manager.cfgSetup.user_stream_decoder_module
        c_name: str = self.manager.cfgSetup.user_stream_decoder_class_name
        decoder_type: type[UserStreamDecoder[Any]] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.manager.set_log(
            f"{decoder_type.__name__} used as {UserStreamDecoder.__name__}"
        )
        self.decoder = decoder_type(
            rest=self.rest,
            base_url=self.url,
            price_mult=self.manager.cfgCoin.price_mult,
            qty_mult=self.manager.cfgCoin.qty_mult,
            scale_mult=self.manager.cfgAccount.scale_mult,
        )
        self.base_uri = self.url

    @override
    async def on_pre_connect(self) -> None:
        self.url: str = await self.decoder.on_pre_connect()

    @override
    async def on_connection(self, ws: ClientConnection) -> None:
        await self.decoder.on_connection(ws)

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        raw_data: bytes = await ws.recv(decode=False)
        if decoded_data := self.decoder.decode(raw_data):
            await self.alarm_clock(
                self.gus_wid,
                self.gus_rid,
                self.gus_cell_amount,
                self.gus_safe_lag,
            )
            if (
                self.set_raw_data(
                    raw_data=decoded_data,
                    writer_id=self.gus_wid,
                    data=self.gus_data,
                    data_header=self.gus_data_header,
                    data_size=self.gus_data_size,
                    cell_amount=self.gus_cell_amount,
                )
                and self.execution_event.is_set() is False
            ):
                self.execution_event.set()
        else:
            self.manager.dump_exc()
            self.manager.set_proc_sc(scs.DECODE_ERROR, wait_main_task=True)
            await ws.close()
