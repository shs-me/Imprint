from typing import Any, override

from websockets import ClientConnection

from imprint.configs import UserStreamDecoder


class BybitUserStreamDecoder(UserStreamDecoder[Any]):
    @override
    async def on_pre_connect(self) -> str: ...

    @override
    async def on_connection(self, ws: ClientConnection) -> None: ...

    @override
    def decode_user_event(
        self, raw_data: bytes | memoryview
    ) -> bytes | None: ...
