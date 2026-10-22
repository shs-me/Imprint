from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast, final

from numpy import int64

from imprint._core.footprint.models.bar import Bar, PriceLike
from imprint._core.footprint.models.base import Chart
from imprint._core.footprint.models.converter import Converter
from imprint._core.utils import FPArray
from imprint._core.utils.base import DPArray, FPHeadersArray, VPArray


@final
@dataclass(slots=True)
class Footprint(Chart):
    """Complete order flow footprint chart containing bars, profiles, and trade data."""

    con: Converter
    last_idx: memoryview

    headers_offset: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    vp: VolumeProfile[Footprint] = field(init=False)
    dp: DeltaProfile[Footprint] = field(init=False)

    _bars: list[Bar] = field(default_factory=list[Bar], init=False)

    def __post_init__(self) -> None:
        self.vp = VolumeProfile(self)
        self.dp = DeltaProfile(self)

    def __getitem__(self, idx: int | int64) -> Bar:
        return self._bars[(idx & ~1) // 2]

    def post_init(self) -> None:
        if self.con.total_bar_count != self.headers.shape[0]:
            self.headers = FPHeadersArray(self.con.total_bar_count)
        else:
            self.headers.fill(0)

        if (self.con.fp_cols[0] // 2) > len(self._bars):
            for idXbid in range(len(self._bars) * 2, self.con.fp_cols[0], 2):
                self._bars.append(Bar(self, idXbid))

        self.headers_offset[0] = 0

    def _re_init_arr(self, nPrice: int64, padding: bool) -> None:  # pyright: ignore[reportUnusedFunction]
        _ = self.con
        # - - -
        need_rows: int = int(nPrice * 20 // 100 // _.scale[0])

        if padding:
            _.fp_rows[0] = _.fp_rows[0] + need_rows

            if nPrice > _.baseNprice[0]:
                before, after = need_rows, 0
                _.center[0] = _.center[0] + need_rows
            else:
                before, after = 0, need_rows

            self.base = self.base.padding(before, after)
            if _.with_state[0]:
                self.state = self.state.padding(before, after)
            if _.with_ctrade[0]:
                self.ctrade = self.ctrade.padding(before, after)

            self.vp._re_init_arr()
            self.dp._re_init_arr()

        else:
            if (rows := (2 * need_rows)) > self.base.shape[0]:
                _.fp_rows[0], cols = rows, _.fp_panel_cols[0]

                self.base = FPArray(rows, cols)
                if _.with_state[0]:
                    self.state = FPArray(rows, cols)
                if _.with_ctrade[0]:
                    self.ctrade = FPArray(rows, cols)

                self.vp._re_init_arr()
                self.dp._re_init_arr()
            else:
                _.fp_rows[0] = self.base.shape[0]

    @property
    def last_bar(self) -> int:
        return (self.last_idx[0] & ~1) // 2

    @property
    def vwap(self) -> PriceLike:
        return self._bars[self.last_bar].ind.fp_vwap

    @property
    def vwap_up_band(self) -> PriceLike:
        return self._bars[self.last_bar].ind.fp_vwap_up_band

    @property
    def vwap_low_band(self) -> PriceLike:
        return self._bars[self.last_bar].ind.fp_vwap_low_band


@dataclass(slots=True)
class VolumeProfile[T]:
    """Manage volume profile analytics across price levels for a footprint chart."""

    _fp: Footprint

    base: VPArray = field(init=False)
    state: VPArray = field(init=False)

    def _re_init_arr(self) -> None:
        self.base = cast(VPArray, self._fp.base[:, self._fp.con.idxVP[0]])
        if self._fp.con.with_state:
            self.state = cast(VPArray, self._fp.state[:, self._fp.con.idxVP[0]])

    @property
    def poc(self) -> PriceLike:
        _ = self._fp
        return _._bars[_.last_bar].ind.fp_poc

    @property
    def vah(self) -> PriceLike:
        _ = self._fp
        return _._bars[_.last_bar].ind.fp_vah

    @property
    def val(self) -> PriceLike:
        _ = self._fp
        return _._bars[_.last_bar].ind.fp_val


@dataclass(slots=True)
class DeltaProfile[T]:
    """Manage delta profile analytics across price levels for a footprint chart."""

    _fp: Footprint

    base: DPArray = field(init=False)
    state: DPArray = field(init=False)

    def _re_init_arr(self) -> None:
        self.base = cast(DPArray, self._fp.base[:, self._fp.con.idxDP[0]])
        if self._fp.con.with_state:
            self.state = cast(DPArray, self._fp.state[:, self._fp.con.idxDP[0]])
