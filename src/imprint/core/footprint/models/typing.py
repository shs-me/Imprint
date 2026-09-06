from typing import Literal, SupportsIndex

T_SLICE = slice[SupportsIndex | None]
T_INDEX = SupportsIndex

T_1D = T_SLICE | T_INDEX

T_IDY = T_1D
T_IDX = T_1D

T_VP = T_IDY
T_BID = Literal[0]
T_ASK = Literal[1]
T_FP = T_IDY | tuple[T_IDY, T_IDX]
T_BAR = T_IDY | tuple[T_IDY, T_BID | T_ASK | T_SLICE]
