from typing import Literal, SupportsIndex

from numpy import bool_
from numpy.typing import NDArray

T_SLICE = slice[SupportsIndex | None]
T_INDEX = SupportsIndex
T_MASK = NDArray[bool_]

T_1D = T_SLICE | T_INDEX

T_IDY = T_1D
T_IDX = T_1D
T_BAR = T_1D

T_BID = Literal[0]
T_ASK = Literal[1]
T_VP = Literal[0]
T_DP = Literal[1]

T_FP = T_BAR | tuple[T_BAR, T_IDY, T_ASK | T_BID | T_SLICE] | T_MASK
T_PROFILE = T_VP | T_DP | T_SLICE | tuple[T_VP | T_DP | T_SLICE, T_IDY] | T_MASK
