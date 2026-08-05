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

        self.clusters = BarClusters(bar=self)
        self.ind = BarIndicators(bar=self)

        self._plike: PriceLike = PriceLike(bar=self)
        self._vlike: VolumeLike = VolumeLike(bar=self)
        self._llike: VolatilityLike = VolatilityLike(bar=self)
        self._tlike: TimeLike = TimeLike(bar=self)

        self._idx: int | int64 = 0

    def __getitem__(self, idx: int | int64):
        self._idx = idx
        return self

    def _get_header(self, header: c.BarHeaders) -> int64:
        """Extracts header value for specified bar index and BarHeaders field."""

        return self._con.headers[(self._idx & ~1) // 2, header]


class BarClusters:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar
        self._create_clusters_mask()

    def _create_clusters_mask(self) -> None:
        idXbid = self._bar._idx & ~1
        idYmin: int64 = self._bar.ind.high.id
        idYmax: int64 = self._bar.ind.low.id

        self._clusters: NDArray[int64] = self._bar._con.footprint[
            idYmin : idYmax + 1, idXbid : idXbid + 2
        ]

        bar_flags = (
            c.SF_OPEN
            | c.SF_HIGH
            | c.SF_LOW
            | c.SF_CLOSE
            | c.SF_POC_BAR
            | c.SF_VAH_BAR
            | c.SF_VAL_BAR
        )
        bid_ask_flags = c.SF_DELTA_DOMINATION | c.SF_IMBALANCE | c.SF_ZERO_PRINT
        mask = bar_flags | bid_ask_flags

        self._clusters_states: NDArray[int32] = (
            self._bar._fp_state[idYmin : idYmax + 1, idXbid : idXbid + 2] & mask
        )

    @property
    def base(self) -> NDArray[int64]:
        return self._clusters

    def states(self) -> NDArray[int32]:
        return self._clusters_states


class BarIndicators:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def open(self):
        self._bar._plike._nPrice = self._bar._get_header(header=c.BarHeaders.Open)
        return self._bar._plike

    @property
    def high(self):
        self._bar._plike._nPrice = self._bar._get_header(header=c.BarHeaders.High)
        return self._bar._plike

    @property
    def low(self):
        self._bar._plike._nPrice = self._bar._get_header(header=c.BarHeaders.Low)
        return self._bar._plike

    @property
    def close(self):
        self._bar._plike._nPrice = self._bar._get_header(header=c.BarHeaders.Close)
        return self._bar._plike

    @property
    def poc(self):
        self._bar._plike._idxBid = self._bar._idx & ~1
        self._bar._plike._nPrice = self._bar._get_header(header=c.BarHeaders.POC)
        return self._bar._plike

    @property
    def vah(self):
        self._bar._plike._idxBid = self._bar._idx & ~1
        self._bar._plike._nPrice = self._bar._get_header(header=c.BarHeaders.VAH)
        return self._bar._plike

    @property
    def val(self):
        self._bar._plike._idxBid = self._bar._idx & ~1
        self._bar._plike._nPrice = self._bar._get_header(header=c.BarHeaders.VAL)
        return self._bar._plike

    @property
    def vwap(self):
        self._bar._plike._idxBid = self._bar._idx & ~1
        self._bar._plike._nPrice = self._bar._get_header(header=c.BarHeaders.VWAP)
        return self._bar._plike

    @property
    def vwap_bb_upper(self):
        self._bar._plike._nPrice = self._bar._get_header(
            header=c.BarHeaders.VWAP_BB_UPPER
        )
        return self._bar._plike

    @property
    def vwap_bb_lower(self):
        self._bar._plike._nPrice = self._bar._get_header(
            header=c.BarHeaders.VWAP_BB_LOWER
        )
        return self._bar._plike

    @property
    def volatility(self):
        return self._bar._llike

    @property
    def time(self):
        return self._bar._tlike

    @property
    def volume(self):
        return self._bar._vlike

    @property
    def delta(self) -> int64:
        return self._bar._get_header(header=c.BarHeaders.Delta)

    @property
    def cvd(self) -> int64:
        return self._bar._get_header(header=c.BarHeaders.CVD)

    @property
    def count_trade(self) -> int64:
        return self._bar._get_header(header=c.BarHeaders.CountTrade)


class PriceLike:
    def __init__(self, bar: Bar) -> None:
        self._con: FPconverter = bar._con

        self._qlike: QtyLike = QtyLike(price_like=self)

        self._nPrice: int64 = int64(0)
        self._idxBid: int | int64 = 0

    @property
    def n(self) -> int64:
        return self._nPrice

    @property
    def id(self) -> int64:
        return self._con.to_idy(self._nPrice)

    @property
    def qty(self):
        return self._qlike


class QtyLike:
    def __init__(self, price_like: PriceLike) -> None:
        self._plike = price_like

    @property
    def delta(self) -> int64:
        return self.bid - self.ask

    @property
    def sum(self) -> int64:
        return self.bid + self.ask

    @property
    def bid(self) -> int64:
        return self._plike._con.footprint[self._plike.id, self._plike._idxBid]

    @property
    def ask(self) -> int64:
        return self._plike._con.footprint[self._plike.id, self._plike._idxBid + 1]


class VolumeLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def n(self) -> int64:
        return self._bar._get_header(c.BarHeaders.Volume)

    @property
    def avg(self) -> int64:
        return self._bar._get_header(c.BarHeaders.AvgVolume)


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
        return self._bar.ind.open.n - self._bar.ind.close.n

    @property
    def change_percent(self) -> float64:
        open, close = self._bar.ind.open.n, self._bar.ind.close.n
        return (close / open - 1) if (close >= open) else -(open / close - 1)

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
            (self._bar._get_header(header=c.BarHeaders.PARK) / c.VAR_SCALE)
            * PARK_FACTOR
        )


class TimeLike:
    def __init__(self, bar: Bar) -> None:
        self._bar = bar

    @property
    def open(self) -> int64:
        return self._bar._get_header(header=c.BarHeaders.OpenTime)

    @property
    def last_trade(self) -> int64:
        return self._bar._get_header(header=c.BarHeaders.LastTradeTime)
