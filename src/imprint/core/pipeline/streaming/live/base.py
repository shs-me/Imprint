import asyncio
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass, field
from typing import final

from msgspec import MsgspecError
from websockets import ClientConnection
from websockets import exceptions as ws_exc
from websockets.asyncio.client import connect

from ....settings import StatusCodes as scs
from ....utils.tools import dump_exception
from ..base import Base as GlobalBase


@dataclass(slots=True)
class Base(GlobalBase, ABC):
    url: str

    exc_counter: Counter[str] = field(default_factory=Counter, init=False)

    @final
    async def run(self) -> None:
        try:
            async for ws in connect(
                self.url, ping_interval=20, ping_timeout=10, close_timeout=5
            ):
                try:
                    self.manager.set_text(f"WS Connected to {self.url}")
                    while True:
                        await self.in_connection(ws)

                except MsgspecError:
                    await ws.close()
                    dump_exception()
                    return self.manager.set_proc_sc(scs.ERROR, wait_main_task=True)

                except (TimeoutError, asyncio.TimeoutError):
                    self.exc_counter[
                        TimeoutError.__name__ or asyncio.TimeoutError.__name__
                    ] += 1
                    self.manager.set_text(
                        "WS Ping timeout (no heartbeat from server). Reconnecting..."
                    )
                except ws_exc.ProtocolError as e:
                    self.exc_counter[ws_exc.ProtocolError.__name__] += 1
                    self.manager.set_text(f"WS Protocol error: {e}. Reconnecting...")

                except ws_exc.PayloadTooBig as e:
                    self.exc_counter[ws_exc.PayloadTooBig.__name__] += 1
                    self.manager.set_text(f"WS Payload too big: {e}. Reconnecting...")

                except ws_exc.InvalidState as e:
                    self.exc_counter[ws_exc.InvalidState.__name__] += 1
                    self.manager.set_text(f"WS Invalid state: {e}. Reconnecting...")

        except (ws_exc.InvalidURI, ws_exc.InvalidProxy) as e:
            self.manager.set_text(f"Fatal WS Config Error: {e}")
            self.manager.set_proc_sc(code=scs.ERROR, wait_main_task=True)

        except ws_exc.InvalidHandshake as e:
            self.manager.set_text(f"Fatal WS Handshake Rejected: {e}")
            self.manager.set_proc_sc(code=scs.ERROR, wait_main_task=True)

        except ws_exc.ConcurrencyError as e:
            self.manager.set_text(f"Fatal WS Concurrency error: {e}")
            self.manager.set_proc_sc(code=scs.ERROR, wait_main_task=True)

        except OSError as e:
            self.manager.set_text(f"WS Network error: {e}.")
            self.manager.set_proc_sc(code=scs.ERROR, wait_main_task=True)

        except asyncio.CancelledError:
            self.manager.set_text("WS stream cancelled.")

    @abstractmethod
    async def in_connection(self, ws: ClientConnection) -> None:
        pass

    @final
    async def alarm_clock(
        self, wid: memoryview, rid: memoryview, cell_amount: int, safe_lag: int
    ) -> None:
        while self.lag_not_is_safe(wid, rid, cell_amount, safe_lag):
            await asyncio.sleep(0)
