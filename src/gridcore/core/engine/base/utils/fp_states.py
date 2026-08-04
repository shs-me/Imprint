from numpy import int32, int64
from numpy.typing import NDArray

from .... import constant as c
from .fp_converter import ConverterLike, FPconverter


class FPstates:
    def __init__(
        self,
        fp_converter: FPconverter,
        fp_state: NDArray[int32],
        fp_state_cache: NDArray[int64],
    ) -> None:
        self._con: FPconverter = fp_converter
        self._fp_state: NDArray[int32] = fp_state
        self._fp_state_cache: NDArray[int64] = fp_state_cache

        self._con_like: ConverterLike = ConverterLike(
            fp_converter=self._con, is_bar=False
        )

        self._idy_range: slice = slice(0, 0)

    def __getitem__(self, idYmin: int64, idYmax: int64):
        self._idy_range = slice(idYmin, idYmax)
        return self

    @property
    def vwap(self):
        self._con_like._idxBid = self._con.idxVP
        self._con_like._idy = self._fp_state_cache[c.CSD_VWAP]
        return self._con_like

    @property
    def poc(self):
        self._con_like._idxBid = self._con.idxVP
        self._con_like._idy = self._fp_state_cache[c.CSD_POC_FP]
        return self._con_like

    @property
    def vah(self):
        self._con_like._idxBid = self._con.idxVP
        self._con_like._idy = self._fp_state_cache[c.CSD_VAH_FP]
        return self._con_like

    @property
    def val(self):
        self._con_like._idxBid = self._con.idxVP
        self._con_like._idy = self._fp_state_cache[c.CSD_VAL_FP]
        return self._con_like

    @property
    def fp_state_mask(self) -> NDArray[int32]:
        state = (
            c.SF_FINISHED_AUCTION
            | c.SF_UNFINISHED_AUCTION
            | c.SF_ASK_DELTA_DOMINATION_FP
            | c.SF_BID_DELTA_DOMINATION_FP
            | c.SF_POC_FP
            | c.SF_VAH_FP
            | c.SF_VAL_FP
            | c.SF_VWAP
        )
        return self._fp_state[self._idy_range, self._con.idxVP] & state
