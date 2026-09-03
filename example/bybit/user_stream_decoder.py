from typing import override

import msgspec

from imprint.api import constant as c
from imprint.api.base import UserStreamDecoder


class BybitUserStreamDecoder(UserStreamDecoder):
    @override
    def __post_init__(self):
        self.decoder = msgspec.json.Decoder()

    @override
    def decode_user_event(self, raw_json: bytes) -> bytes | None:
        pass
