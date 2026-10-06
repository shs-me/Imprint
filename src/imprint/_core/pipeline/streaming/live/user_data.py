import asyncio
import importlib
from dataclasses import dataclass, field
from multiprocessing.synchronize import Event
from typing import Any, override

from websockets import ClientConnection

from imprint._core.pipeline.streaming.live.base import Base
from imprint._core.utils import UserStreamDecoder


@dataclass(slots=True)
class UserData(Base):
    """Consumes authenticated user data and execution streams via WebSocket.

    Parameters
    ----------
    execution_event : Event
        Multiprocessing event signaling successful user execution initialization.

    Attributes
    ----------
    decoder : UserStreamDecoder[Any, Any]
        Exchange-specific user stream decoder instance.
    base_uri : str
        Base WebSocket Uniform Resource Identifier for the user data stream.
    keep_task : asyncio.Task[None] | None
        Background task maintaining session keepalive or heartbeat pulses.
    """

    execution_event: Event

    decoder: UserStreamDecoder[Any, Any] = field(init=False)
    base_uri: str = field(init=False)
    keep_task: asyncio.Task[None] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize the user stream decoder module with coin and account scaling parameters."""
        m_name: str = self.manager.cfgSetup.user_stream_decoder_module
        c_name: str = self.manager.cfgSetup.user_stream_decoder_class_name
        decoder_type: type[UserStreamDecoder[Any, Any]] = getattr(
            importlib.import_module(m_name), c_name
        )
        self.decoder = decoder_type(
            rest=self.rest,
            base_url=self.url,
            price_mult=self.manager.cfgCoin.price_mult,
            qty_mult=self.manager.cfgCoin.qty_mult,
            scale_mult=self.manager.cfgAccount.scale_mult,
        )
        self.manager.set_log(
            f"{decoder_type.__name__} used as {UserStreamDecoder.__name__}"
        )
        self.base_uri = self.url

    @override
    async def on_pre_connect(self) -> None:
        """Fetch connection tokens and negotiate endpoint URL before connecting."""
        self.url: str = await self.decoder.on_pre_connect()

    @override
    async def on_connection(self, ws: ClientConnection) -> None:
        """Execute post-connection actions for the authenticated user stream.

        Parameters
        ----------
        ws : ClientConnection
            Active WebSocket client connection instance.
        """
        await self.decoder.on_connection(ws)

    @override
    async def in_connection(self, ws: ClientConnection) -> None:
        """Receive binary messages from the user stream, decode, and store into the ring buffer.

        Parameters
        ----------
        ws : ClientConnection
            Active WebSocket client connection instance.
        """
        _ = self.manager.cfgUserDataStream
        # - - -
        raw_data: bytes = await ws.recv(decode=False)
        for data in self.decoder.decode(raw_data):
            while _.ring_buf.lag_not_is_safe():
                await asyncio.sleep(0.001)

            _.set_data_in_live(data)

        if self.execution_event.is_set() is False:
            self.execution_event.set()
