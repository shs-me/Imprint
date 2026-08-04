from numpy import int32, int64
from numpy.typing import NDArray

from .bar_states import BarStates
from .fp_converter import FPconverter
from .fp_states import FPstates


class Indicators:
    def __init__(
        self,
        fp_converter: FPconverter,
        fp_state: NDArray[int32],
        fp_state_cache: NDArray[int64],
    ) -> None:
        self._con: FPconverter = fp_converter
        self._fp_state: NDArray[int32] = fp_state
        self._fp_state_cache: NDArray[int64] = fp_state_cache

        self.fp: FPstates = FPstates(
            fp_converter=self._con,
            fp_state=self._fp_state,
            fp_state_cache=self._fp_state_cache,
        )
        self.bar: BarStates = BarStates(
            fp_converter=self._con,
            fp_state=self._fp_state,
        )
