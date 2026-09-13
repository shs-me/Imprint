from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, override

from websockets import ClientConnection

from imprint.configs import BalanceData, OrderData, UserStreamDecoder


@dataclass(slots=True)
class BybitUserStreamDecoder(UserStreamDecoder[Any, Any]):
    @override
    async def on_pre_connect(self) -> str: ...

    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    def decode(
        self, raw_data: bytes | memoryview
    ) -> Iterator[OrderData | BalanceData]: ...
