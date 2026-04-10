from . import FootprintReader


class BaseFootprintReader(FootprintReader):
    def check_patterns(self, idy: int, idx: int) -> None:
        pass
