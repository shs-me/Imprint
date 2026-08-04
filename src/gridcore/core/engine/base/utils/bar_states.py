from numpy import int32, int64
from numpy.typing import NDArray

from .... import constant as c
from .fp_converter import ConverterLike, FPconverter


class BarStates:
    def __init__(self, fp_converter: FPconverter, fp_state: NDArray[int32]) -> None:
        self._con: FPconverter = fp_converter
        self._fp_state: NDArray[int32] = fp_state

        self._con_like: ConverterLike = ConverterLike(
            fp_converter=self._con, is_bar=True
        )
        self._idx: int | int64 = 0

    def __getitem__(self, idx: int | int64):
        self._idx = idx
        return self

    def _get_header(self, header: c.BarHeaders) -> int64:
        """Extracts header value for specified bar index and BarHeaders field."""

        return self._con.headers[(self._idx & ~1) // 2, header]

    @property
    def open(self):
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.Open)
        return self._con_like

    @property
    def high(self):
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.High)
        return self._con_like

    @property
    def low(self):
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.Low)
        return self._con_like

    @property
    def close(self):
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.Close)
        return self._con_like

    @property
    def nVolume(self) -> int64:
        return self._get_header(header=c.BarHeaders.Volume)

    @property
    def nDelta(self) -> int64:
        return self._get_header(header=c.BarHeaders.Delta)

    @property
    def nCvd(self) -> int64:
        return self._get_header(header=c.BarHeaders.CVD)

    @property
    def vwap(self):
        self._con_like._idxBid = self._idx & ~1
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.VWAP)
        return self._con_like

    @property
    def vwap_bb_upper(self):
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.VWAP_BB_UPPER)
        return self._con_like

    @property
    def vwap_bb_lower(self):
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.VWAP_BB_LOWER)
        return self._con_like

    @property
    def poc(self):
        self._con_like._idxBid = self._idx & ~1
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.POC)
        return self._con_like

    @property
    def vah(self):
        self._con_like._idxBid = self._idx & ~1
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.VAH)
        return self._con_like

    @property
    def val(self):
        self._con_like._idxBid = self._idx & ~1
        self._con_like._nPrice = self._get_header(header=c.BarHeaders.VAL)
        return self._con_like

    @property
    def openTime(self) -> int64:
        return self._get_header(header=c.BarHeaders.OpenTime)

    @property
    def lastTradeTime(self) -> int64:
        return self._get_header(header=c.BarHeaders.LastTradeTime)

    @property
    def countTrade(self) -> int64:
        return self._get_header(header=c.BarHeaders.CountTrade)

    @property
    def atr(self) -> int64:
        return self._get_header(header=c.BarHeaders.ATR)

    @property
    def states_mask(self) -> NDArray[int32]:
        idxBid = self._idx & ~1
        idYmin: int64 = self.high.idY
        idYmax: int64 = self.low.idY

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
        return self._fp_state[idYmin : idYmax + 1, idxBid : idxBid + 2] & mask
