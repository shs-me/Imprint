from typing import override

from imprint.api.setup import UserStreamDecoder


class BybitUserStreamDecoder(UserStreamDecoder):
    @override
    def __post_init__(self):
        pass

    @override
    def decode_user_event(self, raw_json: bytes) -> bytes | None:
        pass
