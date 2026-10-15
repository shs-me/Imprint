from typing import Literal, SupportsIndex

from numpy import bool_
from numpy.typing import NDArray

T_SLICE = slice[SupportsIndex | None]
T_INDEX = SupportsIndex
T_MASK = NDArray[bool_]

T_1D = T_SLICE | T_INDEX

T_IDY = T_1D
T_IDX = T_1D

T_VP = T_IDY
T_BID = Literal[0]
T_ASK = Literal[1]
T_FP = T_IDY | tuple[T_IDY, T_IDX | T_ASK | T_BID] | T_MASK
