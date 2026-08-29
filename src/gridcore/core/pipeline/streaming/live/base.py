import asyncio
from abc import ABC, abstractmethod

from websockets import ClientConnection
from websockets import exceptions as ws_exc
from websockets.asyncio.client import connect

from ....ipc.manager import NodeManager
from ..base import Base as GlobalBase


class Base(GlobalBase, ABC):
    def __init__(self, manager: NodeManager, url: str) -> None:
        super().__init__(manager)

        self.url: str = url

    async def run(self) -> None:
        async for ws in connect(self.url):
            try:
                while True:
                    await self.in_connection(ws)

            except ws_exc.ConnectionClosed:
                return
            except ws_exc.InvalidURI:
                return
            except ws_exc.InvalidProxy:
                return
            except ws_exc.InvalidHandshake:
                return
            except ws_exc.InvalidState:
                return
            except ws_exc.ProtocolError:
                return
            except ws_exc.PayloadTooBig:
                return
            except ws_exc.ConcurrencyError:
                return

    @abstractmethod
    async def in_connection(self, ws: ClientConnection) -> None:
        pass

    async def alarm_clock(
        self, wid: memoryview, rid: memoryview, cell_amount: int, safe_lag: int
    ) -> None:
        while self.lag_not_is_safe(wid, rid, cell_amount, safe_lag):
            await asyncio.sleep(0)
