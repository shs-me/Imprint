from __future__ import annotations

from numba.core.types import np
from numpy import float64, int32, int64
from numpy.typing import NDArray

from .... import constant as c
from .fp_converter import FPconverter

PARK_FACTOR: int = 1.0 / (4.0 * np.log(2.0))


class Bar:
    def __init__(self, fp_converter: FPconverter, fp_state: NDArray[int32]) -> None:
        self._con: FPconverter = fp_converter
        self._fp_state: NDArray[int32] = fp_state

        self._vplike: VolumeProfileLike = VolumeProfileLike(bar=self)
        self._dplike: DeltaProfileLike = DeltaProfileLike(bar=self)
        self._indlike: IndicatorLike = IndicatorLike(bar=self)

        self._plike: PriceLike = PriceLike(bar=self)
        self._qlike: QtyLike = QtyLike(bar=self)
        self._vlike: VolumeLike = VolumeLike(bar=self)
        self._llike: VolatilityLike = VolatilityLike(bar=self)
        self._trlike: TradeLike = TradeLike(bar=self)
        self._tilike: TimeLike = TimeLike(bar=self)
        self._fplike: FPindLike = FPindLike(bar=self)

        self._idx: int | int64 = 0
        self._idXbid: int | int64 = 0
        self._bar_id: int | int64 = 0

    def __getitem__(self, idx: int | int64):
        self._idx = idx
        self._idXbid = self._idx & ~1
        self._bar_id = self._idXbid // 2
        return self

    def _get_header(self, header: c.BarHeaders) -> int64:
        """Extracts header value for specified bar index and BarHeaders field."""

        return self._con.headers[self._bar_id, header]

    @property
    def base(self) -> NDArray[int64]:
        idYmin, idYmax = self.ind.high.id, self.ind.low.id
        return self._con.footprint[idYmin : idYmax + 1, self._idXbid : self._idXbid + 2]

    @property
    def bid(self) -> NDArray[int64]:
        idYmin, idYmax = self.ind.high.id, self.ind.low.id
        return self._con.footprint[idYmin : idYmax + 1, self._idXbid]

    @property
    def ask(self) -> NDArray[int64]:
        idYmin, idYmax = self.ind.high.id, self.ind.low.id
        return self._con.footprint[idYmin : idYmax + 1, self._idXbid + 1]

    @property
    def state(self) -> NDArray[int32]:
        idYmin, idYmax = self.ind.high.id, self.ind.low.id
        return self._fp_state[idYmin : idYmax + 1, self._idXbid : self._idXbid + 2]

    @property
    def vp(self) -> VolumeProfileLike:
        return self._vplike

    @property
    def dp(self) -> DeltaProfileLike:
        return self._dplike

    @property
    def ind(self) -> IndicatorLike:
        return self._indlike


class VolumeProfileLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def base(self) -> NDArray[int64]:
        return self._bar.bid + self._bar.ask

    @property
    def poc(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.POC)
        return self._bar._plike

    @property
    def vah(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VAH)
        return self._bar._plike

    @property
    def val(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VAL)
        return self._bar._plike


class DeltaProfileLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def base(self) -> NDArray[int64]:
        return self._bar.bid - self._bar.ask

    @property
    def delta(self) -> int64:
        return self._bar._get_header(c.BarHeaders.Delta)

    @property
    def cvd(self) -> int64:
        return self._bar._get_header(c.BarHeaders.CVD)

    @property
    def delta_ratio(self) -> float:
        return self.delta / self._bar.ind.volume.n

    @property
    def poc(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.POC)
        return self._bar._plike

    @property
    def vah(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VAH)
        return self._bar._plike

    @property
    def val(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VAL)
        return self._bar._plike


class IndicatorLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def open(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.Open)
        return self._bar._plike

    @property
    def high(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.High)
        return self._bar._plike

    @property
    def low(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.Low)
        return self._bar._plike

    @property
    def close(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.Close)
        return self._bar._plike

    @property
    def volume(self) -> VolumeLike:
        return self._bar._vlike

    @property
    def time(self) -> TimeLike:
        return self._bar._tilike

    @property
    def trade(self) -> TradeLike:
        return self._bar._trlike

    @property
    def volatility(self) -> VolatilityLike:
        return self._bar._llike

    @property
    def fp_ind(self) -> FPindLike:
        return self._bar._fplike


class PriceLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

        self._nPrice: int64 = int64(0)

    @property
    def n(self) -> int64:
        return self._nPrice

    @property
    def id(self) -> int64:
        return self._bar._con.to_idy(self._nPrice)

    @property
    def qty(self):
        return self._bar._qlike


class QtyLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def delta(self) -> int64:
        return self.bid - self.ask

    @property
    def sum(self) -> int64:
        return self.bid + self.ask

    @property
    def bid(self) -> int64:
        return self._bar._con.footprint[self._bar._plike.id, self._bar._idXbid]

    @property
    def ask(self) -> int64:
        return self._bar._con.footprint[self._bar._plike.id, self._bar._idXbid + 1]


class VolumeLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def n(self) -> int64:
        return self._bar._get_header(c.BarHeaders.Volume)

    @property
    def avg(self) -> int64:
        bar_min, bar_max = max(0, self._bar._bar_id - 20), self._bar._bar_id + 1
        return int64(
            self._bar._con.headers[bar_min:bar_max, c.BarHeaders.Volume].mean()
        )

    @property
    def avg_trade_size(self) -> int64:
        return self.n // self._bar.ind.trade.count


class VolatilityLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def range(self) -> int64:
        return self._bar.ind.high.n - self._bar.ind.low.n

    @property
    def range_percent(self) -> float64:
        return self._bar.ind.high.n / self._bar.ind.low.n - 1

    @property
    def change(self) -> int64:
        return self._bar.ind.close.n - self._bar.ind.open.n

    @property
    def change_percent(self) -> float64:
        open, close = self._bar.ind.open.n, self._bar.ind.close.n
        return (close / open - 1) if (close >= open) else -abs(open / close - 1)

    @property
    def atr(self) -> int64:
        return self._bar._get_header(c.BarHeaders.ATR)

    @property
    def atr_percent(self) -> float64:
        close, atr = self._bar.ind.close.n, self.atr
        return ((atr + close) / close) - 1

    @property
    def parkinson_percent(self) -> float64:
        return np.sqrt(
            (self._bar._get_header(c.BarHeaders.PARK) / c.VAR_SCALE) * PARK_FACTOR
        )


class TradeLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def count(self) -> int64:
        return self._bar._get_header(c.BarHeaders.CountTrade)

    @property
    def avg_count(self) -> int64:
        bar_min, bar_max = max(0, self._bar._bar_id - 20), self._bar._bar_id + 1
        return self._bar._con.headers[bar_min:bar_max, c.BarHeaders.CountTrade].mean()


class TimeLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def open(self) -> int64:
        return self._bar._get_header(header=c.BarHeaders.OpenTime)

    @property
    def last_trade(self) -> int64:
        return self._bar._get_header(header=c.BarHeaders.LastTradeTime)


class FPindLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def vwap(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VWAP)
        return self._bar._plike

    @property
    def vwap_upper_band(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VWAP_UPPER_BAND)
        return self._bar._plike

    @property
    def vwap_lower_band(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VWAP_LOWER_BAND)
        return self._bar._plike

    @property
    def poc(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.POC_FP)
        return self._bar._plike

    @property
    def vah(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VAH_FP)
        return self._bar._plike

    @property
    def val(self) -> PriceLike:
        self._bar._plike._nPrice = self._bar._get_header(c.BarHeaders.VAL_FP)
        return self._bar._plike
