from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, final, override

import numpy as np
from numpy import float64, int64

from imprint._core import constant as c
from imprint._core.footprint.models.base import Chart, PriceLike, QtyLike
from imprint._core.utils import FPArray
from imprint._core.utils.base import DPArray, VPArray

if TYPE_CHECKING:
    from imprint._core.typing import T_ASK, T_BID

PARK_FACTOR: int = 1.0 / (4.0 * np.log(2.0))


@final
@dataclass(slots=True)
class Bar:
    """Represents a single bar and its associated indicators, volume profile, and delta profile.

    Parameters
    ----------
    _fp : Chart
        Parent chart instance containing header data and array buffers.

    Attributes
    ----------
    ind : Indicators[Bar]
        Indicator metrics interface for the active bar.
    vp : VolumeProfile[Bar]
        Volume profile analytics interface for the active bar.
    dp : DeltaProfile[Bar]
        Delta profile analytics interface for the active bar.
    idx : int | int64
        Raw bar index identifier.
    idXbid : int | int64
        Even-aligned index pointing to the bid column.
    bar_id : int | int64
        Calculated header row ID for the bar.
    bar_side : T_BID | T_ASK
        Side indicator (0 for bid, 1 for ask).
    base : FPArray, read-only
        Sliced base array view restricted to the price range and columns of the active bar.
    state : FPArray, read-only
        Sliced state array view restricted to the price range and columns of the active bar.
    ctrade : FPArray, read-only
        Sliced cumulative trade array view restricted to the price range and columns of the active bar.
    """

    _fp: Chart

    ind: Indicators[Bar] = field(init=False)
    vp: VolumeProfile[Bar] = field(init=False)
    dp: DeltaProfile[Bar] = field(init=False)

    idx: int | int64 = field(default=0, init=False)
    idXbid: int | int64 = field(default=0, init=False)
    bar_id: int | int64 = field(default=0, init=False)
    bar_side: T_BID | T_ASK = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.ind = Indicators(self)
        self.vp = VolumeProfile(self)
        self.dp = DeltaProfile(self)

    def __getitem__(self, idx: int | int64) -> Bar:
        """Select a bar by its index and compute alignment coordinates and headers.

        Parameters
        ----------
        idx : int | int64
            Bar index identifier.

        Returns
        -------
        Bar
            The configured bar instance.
        """
        self.idx = idx
        self.idXbid = self.idx & ~1
        self.bar_id = self._fp.headers_offset[0] + (self.idXbid // 2)
        self.bar_side = 1 if self.idx != self.idXbid else 0
        return self

    def _get_header(self, header: int) -> int64:
        return self._fp.headers[self.bar_id, header]

    def __view_bar(self, arr: FPArray) -> FPArray:
        idYmin, idYmax = self.ind.high.id, self.ind.low.id
        return arr[idYmin : idYmax + 1, self.idXbid : self.idXbid + 2]

    @property
    def base(self) -> FPArray:
        return self.__view_bar(self._fp.base)

    @property
    def state(self) -> FPArray:
        return self.__view_bar(self._fp.state)

    @property
    def ctrade(self) -> FPArray:
        return self.__view_bar(self._fp.ctrade)


@final
@dataclass(slots=True)
class Indicators[T]:
    """Exposes technical indicators and statistical metrics for the active bar.

    Parameters
    ----------
    _bar : Bar
        Parent bar instance.

    Attributes
    ----------
    open : PriceLike[T], read-only
        Bar opening price.
    high : PriceLike[T], read-only
        Bar high price.
    low : PriceLike[T], read-only
        Bar low price.
    close : PriceLike[T], read-only
        Bar closing price.
    open_time : int64, read-only
        Bar opening timestamp in milliseconds or microseconds.
    last_trade_time : int64, read-only
        Timestamp of the last trade in the bar.
    volume : int64, read-only
        Total traded volume in the bar.
    ma_volume : int64, read-only
        Moving average of bar volume.
    trade_count : int64, read-only
        Total number of trades executed in the bar.
    ma_trade_count : int64, read-only
        Moving average of trade counts.
    avg_trade_size : int64, read-only
        Average trade size computed as volume divided by trade count.
    ma_avg_trade_size : int64, read-only
        Moving average of average trade sizes.
    delta : int64, read-only
        Net delta (ask volume minus bid volume) for the bar.
    delta_ratio : float, read-only
        Ratio of net delta to total volume.
    cvd : int64, read-only
        Cumulative volume delta.
    range : int64, read-only
        Price range between high and low.
    range_percent : float64, read-only
        Percentage price range relative to low price.
    change : int64, read-only
        Price change between close and open.
    change_percent : float64, read-only
        Percentage price change relative to open price.
    atr : int64, read-only
        Average True Range.
    atr_percent : float64, read-only
        ATR percentage relative to close price.
    parkinson_percent : float64, read-only
        Parkinson volatility percentage estimate.
    fp_vwap : PriceLike[T], read-only
        Footprint Volume-Weighted Average Price.
    fp_vwap_up_band : PriceLike[T], read-only
        Footprint upper VWAP band.
    fp_vwap_low_band : PriceLike[T], read-only
        Footprint lower VWAP band.
    fp_poc : PriceLike[T], read-only
        Footprint Point of Control.
    fp_vah : PriceLike[T], read-only
        Footprint Value Area High.
    fp_val : PriceLike[T], read-only
        Footprint Value Area Low.
    """

    _bar: Bar

    __plike: PriceLike[T] = field(init=False)

    def __post_init__(self) -> None:
        self.__plike = PriceLike(self._bar._fp.con, Qty(self._bar))

    @property
    def open(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_Open)]

    @property
    def high(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_High)]

    @property
    def low(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_Low)]

    @property
    def close(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_Close)]

    @property
    def open_time(self) -> int64:
        return self._bar._get_header(header=c.BH_Time)

    @property
    def last_trade_time(self) -> int64:
        return self._bar._get_header(header=c.BH_LastTradeTime)

    @property
    def volume(self) -> int64:
        return self._bar._get_header(c.BH_Volume)

    @property
    def ma_volume(self) -> int64:
        return self._bar._get_header(c.BH_MA_VOL)

    @property
    def trade_count(self) -> int64:
        return self._bar._get_header(c.BH_CountTrade)

    @property
    def ma_trade_count(self) -> int64:
        return self._bar._get_header(c.BH_MA_COUNT_TRADE)

    @property
    def avg_trade_size(self) -> int64:
        return self.volume // self.trade_count

    @property
    def ma_avg_trade_size(self) -> int64:
        return self._bar._get_header(c.BH_MA_ATS)

    @property
    def delta(self) -> int64:
        return self._bar._get_header(c.BH_Delta)

    @property
    def delta_ratio(self) -> float:
        return self.delta / self.volume

    @property
    def cvd(self) -> int64:
        return self._bar._get_header(c.BH_CVD)

    @property
    def range(self) -> int64:
        return self.high.n - self.low.n

    @property
    def range_percent(self) -> float64:
        return self.high.n / self.low.n - 1

    @property
    def change(self) -> int64:
        return self.close.n - self.open.n

    @property
    def change_percent(self) -> float64:
        return self.close.n / self.open.n - 1

    @property
    def atr(self) -> int64:
        return self._bar._get_header(c.BH_ATR)

    @property
    def atr_percent(self) -> float64:
        close = self.close.n
        return ((self.atr + close) / close) - 1

    @property
    def parkinson_percent(self) -> float64:
        return np.sqrt(
            (self._bar._get_header(c.BH_PARK) / c.VAR_SCALE) * PARK_FACTOR
        )

    @property
    def fp_vwap(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_VWAP)]

    @property
    def fp_vwap_up_band(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_VWAP_UPPER_BAND)]

    @property
    def fp_vwap_low_band(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_VWAP_LOWER_BAND)]

    @property
    def fp_poc(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_POC_FP)]

    @property
    def fp_vah(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_VAH_FP)]

    @property
    def fp_val(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_VAL_FP)]


@final
@dataclass(slots=True)
class VolumeProfile[T]:
    """Computes volume profile aggregates for the active bar.

    Parameters
    ----------
    _bar : Bar
        Parent bar instance.

    Attributes
    ----------
    base : VPArray, read-only
        Aggregated volume profile array combining bid and ask columns for the bar.
    poc : PriceLike[T], read-only
        Point of Control (POC) price level with the highest volume in the bar.
    vah : PriceLike[T], read-only
        Value Area High (VAH) price level for the bar.
    val : PriceLike[T], read-only
        Value Area Low (VAL) price level for the bar.
    """

    _bar: Bar

    __plike: PriceLike[T] = field(init=False)

    def __post_init__(self) -> None:
        self.__plike = PriceLike(self._bar._fp.con, Qty(self._bar))

    @property
    def base(self) -> VPArray:
        bar = self._bar.base
        return bar[:, 0] + bar[:, 1]  # pyright: ignore[reportReturnType]

    @property
    def poc(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_POC)]

    @property
    def vah(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_VAH)]

    @property
    def val(self) -> PriceLike[T]:
        return self.__plike[self._bar._get_header(c.BH_VAL)]


@final
@dataclass(slots=True)
class DeltaProfile[T]:
    """Computes delta profile aggregates (bid-ask difference) for the active bar.

    Parameters
    ----------
    _bar : Bar
        Parent bar instance.

    Attributes
    ----------
    base : DPArray, read-only
        Aggregated delta profile array (bid minus ask volume) for the bar.
    """

    _bar: Bar

    @property
    def base(self) -> DPArray:
        bar = self._bar.base
        return bar[:, 0] - bar[:, 1]  # pyright: ignore[reportReturnType]


@final
@dataclass(slots=True)
class Qty[T](QtyLike[T]):
    """Provides volume, delta, bid, and ask quantities at specific price level indices for a bar.

    Parameters
    ----------
    _bar : Bar
        Parent bar instance.

    Attributes
    ----------
    volume : int64, read-only
        Traded volume at the configured price index and bar side.
    delta : int64, read-only
        Net delta (bid minus ask volume) at the configured price index.
    sum : int64, read-only
        Total volume (bid plus ask volume) at the configured price index.
    bid : int64, read-only
        Bid volume at the configured price index.
    ask : int64, read-only
        Ask volume at the configured price index.
    """

    _bar: Bar

    @override
    def __getitem__(self, idy: int64) -> Qty[T]:
        """Configure the target price level index for bar quantity queries.

        Parameters
        ----------
        idy : int64
            Price level index coordinate.

        Returns
        -------
        Qty[T]
            The current instance configured with the specified index.
        """
        self._idy = idy
        return self

    @property
    def volume(self) -> int64:
        return self._bar._fp.base[self._idy, self._bar.idx]

    @property
    def delta(self) -> int64:
        return self.bid - self.ask

    @property
    def sum(self) -> int64:
        return self.bid + self.ask

    @property
    def bid(self) -> int64:
        return self._bar._fp.base[self._idy, self._bar.idXbid]

    @property
    def ask(self) -> int64:
        return self._bar._fp.base[self._idy, self._bar.idXbid + 1]
