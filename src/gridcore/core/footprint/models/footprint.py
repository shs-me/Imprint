from __future__ import annotations

from numpy import int32, int64
from numpy.typing import NDArray

from ... import constant as c
from .bar import BarLike
from .converter import Converter


class FootprintLike:
    def __init__(
        self,
        converter: Converter,
        headers: NDArray[int64],
        fp: NDArray[int64],
        fp_state: NDArray[int32],
        fp_state_cache: NDArray[int64],
    ) -> None:
        self._con: Converter = converter
        self._headers: NDArray[int64] = headers
        self._fp: NDArray[int64] = fp
        self._fp_state: NDArray[int32] = fp_state
        self._fp_state_cache: NDArray[int64] = fp_state_cache

        self._bar: BarLike = BarLike(
            converter=self._con,
            headers=self._headers,
            fp=self._fp,
            fp_state=self._fp_state,
        )

        self._vplike: VolumeProfileLike = VolumeProfileLike(fp=self)
        self._dplike: DeltaProfileLike = DeltaProfileLike(fp=self)
        self._plike: PriceLike = PriceLike(fp=self)

    @property
    def base(self) -> NDArray[int64]:
        return self._fp

    @property
    def state(self) -> NDArray[int32]:
        return self._fp_state

    @property
    def bar(self) -> BarLike:
        return self._bar

    @property
    def vp(self) -> VolumeProfileLike:
        return self._vplike

    @property
    def dp(self) -> DeltaProfileLike:
        return self._dplike

    @property
    def vwap(self) -> PriceLike:
        self._plike._idy = self._fp_state_cache[c.CSD_VWAP]
        return self._plike

    @property
    def vwap_band_lower(self) -> PriceLike:
        self._plike._idy = self._fp_state_cache[c.CSD_LOWER_BB]
        return self._plike

    @property
    def vwap_band_upper(self) -> PriceLike:
        self._plike._idy = self._fp_state_cache[c.CSD_UPPER_BB]
        return self._plike


class VolumeProfileLike:
    def __init__(self, fp: FootprintLike) -> None:
        self._fp: FootprintLike = fp
        self._idx: int = self._fp._con.idxVP

    @property
    def base(self) -> NDArray[int64]:
        return self._fp.base[:, self._idx]

    @property
    def state(self) -> NDArray[int32]:
        return self._fp.state[:, self._idx]

    @property
    def poc(self) -> PriceLike:
        self._fp._plike._idy = self._fp._fp_state_cache[c.CSD_POC_FP]
        return self._fp._plike

    @property
    def vah(self) -> PriceLike:
        self._fp._plike._idy = self._fp._fp_state_cache[c.CSD_VAH_FP]
        return self._fp._plike

    @property
    def val(self) -> PriceLike:
        self._fp._plike._idy = self._fp._fp_state_cache[c.CSD_VAL_FP]
        return self._fp._plike


class DeltaProfileLike:
    def __init__(self, fp: FootprintLike) -> None:
        self._fp: FootprintLike = fp
        self._idx: int = self._fp._con.idxVP

    @property
    def base(self) -> NDArray[int64]:
        return self._fp.base[:, self._idx]

    @property
    def state(self) -> NDArray[int32]:
        return self._fp.state[:, self._idx]


class PriceLike:
    def __init__(self, fp: FootprintLike) -> None:
        self._fp: FootprintLike = fp

        self._idy: int64 = int64(0)

    @property
    def n(self) -> int | int64:
        return self._fp._con.to_nPrice(self._idy)

    @property
    def id(self) -> int64:
        return self._idy
