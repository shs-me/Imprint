from abc import ABC, abstractmethod


class UserStreamDecoder(ABC):
    @abstractmethod
    def decode_user_event(self, raw_json: bytes) -> bytes | None:
        """return @8q or None"""
        pass
