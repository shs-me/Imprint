import asyncio
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import final

from msgspec import MsgspecError
from websockets import ClientConnection
from websockets import exceptions as ws_exc
from websockets.asyncio.client import connect

from imprint._core.pipeline.streaming.base import Base as GlobalBase
from imprint._core.utils.base_adapters import ExchangeREST


@dataclass(slots=True)
class Base(GlobalBase, ABC):
    """Abstract base class for live WebSocket streaming pipeline components.

    Manages persistent WebSocket connections, automated reconnection logic, heartbeat
    ping intervals, and exception counters.

    Parameters
    ----------
    rest : ExchangeREST
        REST API client adapter for exchange interaction.
    url : str
        Target WebSocket endpoint URL for the live stream connection.

    Attributes
    ----------
    rest : ExchangeREST
        REST API client adapter for exchange interaction.
    url : str
        Target WebSocket endpoint URL for the live stream connection.
    exc_counter : Counter[str]
        Running tally of encountered connection exceptions grouped by exception class name.
    """

    rest: ExchangeREST
    url: str

    exc_counter: Counter[str] = field(default_factory=Counter, init=False)

    @final
    async def run(self) -> None:
        """Execute the primary asynchronous WebSocket connection and message processing loop.

        Handles automatic reconnections on transient dropouts, heartbeat timeouts,
        protocol errors, and fatal configuration or handshake rejections.
        """
        try:
            while True:
                try:
                    await self.on_pre_connect()
                    async with connect(
                        self.url,
                        ping_interval=20,
                        ping_timeout=10,
                        close_timeout=5,
                    ) as ws:
                        try:
                            self.manager.set_log(
                                f"{self.stream} WS Connected to {self.url}"
                            )
                            await self.on_connection(ws)
                            while True:
                                await self.in_connection(ws)

                        except MsgspecError as e:
                            self.manager.set_log(
                                f"{self.stream} msgspec error: {e}."
                            )
                            return self.manager.dump_exc()

                except ws_exc.ConnectionClosedOK:
                    self.manager.set_log(
                        f"{self.stream} {ws_exc.ConnectionClosedOK.__name__}"
                    )

                except ws_exc.ConnectionClosedError as e:
                    self.exc_counter[ws_exc.ConnectionClosedError.__name__] += 1
                    self.manager.set_log(
                        f"{self.stream} WS Connection closed with error: {e}. Reconnecting..."
                    )

                except TimeoutError:
                    self.exc_counter[TimeoutError.__name__] += 1
                    self.manager.set_log(
                        f"{self.stream} WS Ping timeout (no heartbeat from server). Reconnecting..."
                    )

                except ws_exc.ProtocolError as e:
                    self.exc_counter[ws_exc.ProtocolError.__name__] += 1
                    self.manager.set_log(
                        f"{self.stream} WS Protocol error: {e}. Reconnecting..."
                    )

                except ws_exc.PayloadTooBig as e:
                    self.exc_counter[ws_exc.PayloadTooBig.__name__] += 1
                    self.manager.set_log(
                        f"{self.stream} WS Payload too big: {e}. Reconnecting..."
                    )

                except ws_exc.InvalidState as e:
                    self.exc_counter[ws_exc.InvalidState.__name__] += 1
                    self.manager.set_log(
                        f"{self.stream} WS Invalid state: {e}. Reconnecting..."
                    )

        except (ws_exc.InvalidURI, ws_exc.InvalidProxy) as e:
            self.manager.set_log(f"{self.stream} Fatal WS Config Error: {e}")
            self.manager.dump_exc(True)

        except ws_exc.InvalidHandshake as e:
            self.manager.set_log(
                f"{self.stream} Fatal WS Handshake Rejected: {e}"
            )
            self.manager.dump_exc(True)

        except ws_exc.ConcurrencyError as e:
            self.manager.set_log(
                f"{self.stream} Fatal WS Concurrency error: {e}"
            )
            self.manager.dump_exc(True)

        except OSError as e:
            self.manager.set_log(f"{self.stream} WS Network error: {e}.")
            self.manager.dump_exc(True)

        except asyncio.CancelledError:
            self.manager.set_log(f"{self.stream} WS stream cancelled.")

    @abstractmethod
    async def on_pre_connect(self) -> None:
        """Execute asynchronous preparation logic prior to establishing a WebSocket connection."""

    @abstractmethod
    async def on_connection(self, ws: ClientConnection) -> None:
        """Execute initialization actions immediately after a WebSocket connection is established.

        Parameters
        ----------
        ws : ClientConnection
            Active WebSocket client connection instance.
        """

    @abstractmethod
    async def in_connection(self, ws: ClientConnection) -> None:
        """Process incoming messages and events within an active WebSocket session.

        Parameters
        ----------
        ws : ClientConnection
            Active WebSocket client connection instance.
        """

    @final
    @property
    def stream(self) -> str:
        """Get the standardized log prefix string for the stream class.

        Returns
        -------
        str
            Formatted stream identifier prefix.
        """
        return self.__class__.__name__ + " -"
