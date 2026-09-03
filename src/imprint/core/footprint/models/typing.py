from typing import Literal, SupportsIndex, TypeAlias

T_SLICE: TypeAlias = slice[SupportsIndex | None]
T_INDEX: TypeAlias = SupportsIndex

T_1D: TypeAlias = T_SLICE | T_INDEX

T_IDY: TypeAlias = T_1D
T_IDX: TypeAlias = T_1D

T_VP: TypeAlias = T_IDY
T_BID: TypeAlias = Literal[0]
T_ASK: TypeAlias = Literal[1]
T_FP: TypeAlias = T_IDY | tuple[T_IDY, T_IDX]
T_BAR: TypeAlias = T_IDY | tuple[T_IDY, T_BID | T_ASK | T_SLICE]
