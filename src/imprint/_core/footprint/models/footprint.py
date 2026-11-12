from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from imprint._core.footprint.models.bar import Bar, PriceLike
from imprint._core.footprint.models.base import (
    BarsArray,
    Chart,
    DPArray,
    ProfileArray,
    VPArray,
)


@final
@dataclass(slots=True)
class Footprint(Chart):
    """Complete order flow footprint chart containing bars, profiles, and trade data."""

    vp: VolumeProfile[Footprint] = field(init=False)
    dp: DeltaProfile[Footprint] = field(init=False)

    _bars: list[Bar] = field(default_factory=list[Bar], init=False)

    def __post_init__(self) -> None:
        self.vp = VolumeProfile(self)
        self.dp = DeltaProfile(self)

    def __getitem__(self, key: int) -> Bar:
        return self._bars[key]

    def post_init(self) -> None:
        _ = self.con
        bc, bh = _.bar_count[0], _.bar_height[0]
        # - - -
        if (bc != self.base.shape[0]) or (bh != self.base.shape[1]):
            self.base = BarsArray(bc, bh, _.with_state[0], _.with_ctrade[0])

        if _.profile_height[0] > self.profile.shape[0]:
            self.profile = ProfileArray(_.profile_height[0])

        if _.bar_count[0] > len(self._bars):
            for cur_bar in range(len(self._bars), _.bar_count[0]):
                self._bars.append(Bar(self, cur_bar))

    @property
    def vwap(self) -> PriceLike:
        return self._bars[self.last_bar[0]].ind.fp_vwap

    @property
    def vwap_up_band(self) -> PriceLike:
        return self._bars[self.last_bar[0]].ind.fp_vwap_up_band

    @property
    def vwap_low_band(self) -> PriceLike:
        return self._bars[self.last_bar[0]].ind.fp_vwap_low_band


@dataclass(slots=True)
class VolumeProfile[T]:
    """Manage volume profile analytics across price levels for a footprint chart."""

    _fp: Footprint

    @property
    def base(self) -> VPArray:
        return self._fp.profile[0, :]

    @property
    def poc(self) -> PriceLike:
        _ = self._fp
        return _._bars[_.last_bar[0]].ind.fp_poc

    @property
    def vah(self) -> PriceLike:
        _ = self._fp
        return _._bars[_.last_bar[0]].ind.fp_vah

    @property
    def val(self) -> PriceLike:
        _ = self._fp
        return _._bars[_.last_bar[0]].ind.fp_val


@dataclass(slots=True)
class DeltaProfile[T]:
    """Manage delta profile analytics across price levels for a footprint chart."""

    _fp: Footprint

    @property
    def base(self) -> DPArray:
        return self._fp.profile[1, :]
