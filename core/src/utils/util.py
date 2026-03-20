from decimal import Decimal


class ConvertMetrics:
    def __init__(
        self,
        tick_size: float,
        base_price: float,
        base_timestamp: int,
        center: int,
        lines: int,
        cols: int,
        ims: int,
    ) -> None:
        # Initialization
        self.tick_size: float = tick_size
        self.base_price: float = base_price
        self.base_timestamp: int = base_timestamp
        self.center: int = center
        self.lines: int = lines
        self.cols: int = cols
        self.ims: int = ims
        # Init Session
        self.precision: int = abs(
            Decimal(str(self.tick_size)).normalize().as_tuple().exponent  # type: ignore
        )

    def round_to_tick(
        self,
        price: float,
    ) -> float:
        steps = round(price / self.tick_size)
        return round(steps * self.tick_size, self.precision)

    def to_idy(
        self,
        price: float,
    ) -> int | None:
        """
        IF 0 <= ID-Y < Lines, Return ID-Y | Else, Return None
        """
        idy = round(((self.base_price - price) / self.tick_size)) + self.center

        if 0 <= idy < self.lines:
            return idy
        else:
            return None

    def to_idx(
        self,
        timestamp: int,
        is_sell: bool,
    ) -> int | None:
        """
        is_sell: True is bid, False ask.\n
        IF 0 <= ID-X < Cols, Return ID-X | Else, Return None.
        """
        idx: int = round((timestamp - self.base_timestamp) / self.ims) * 2 + (
            0 if is_sell else 1
        )
        if 0 <= idx < self.cols:
            return idx
        else:
            return None

    def to_price(
        self,
        idy: int,
    ) -> float:
        """
        Return Price.
        """
        price: float = self.base_price + ((self.center - idy) * self.tick_size)
        return price

    def to_timestamp(
        self,
        idx: int,
    ) -> int:
        """
        Return Timestamp.
        """
        timestamp: int = (
            round((idx - (0 if idx % 2 == 0 else 1)) / 2) * self.ims
            + self.base_timestamp
        )
        return timestamp
