from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Self, final

import numpy as np
from numpy import int64

import imprint._core.constant as c
from imprint._core.footprint.models.converter import Converter


@dataclass(slots=True)
class Chart(ABC):
    con: Converter = field(default_factory=lambda: Converter(), init=False)
    base: BarsArray = field(default_factory=lambda: BarsArray(0, 0), init=False)
    profile: ProfileArray = field(
        default_factory=lambda: ProfileArray(0), init=False
    )
    headers: BarsHeadersArray = field(
        default_factory=lambda: BarsHeadersArray(10_000), init=False
    )
    headers_offset: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )
    last_bar: memoryview = field(
        default_factory=lambda: memoryview(bytearray(8)).cast("q"), init=False
    )


class BarsArray(np.ndarray):
    def __new__(
        cls, count: int, height: int, with_state: int = 0, with_ctrade: int = 0
    ) -> Self:
        cols = 2
        if with_state:
            cols += 2
        if with_ctrade:
            cols += 2

        obj = super().__new__(cls, shape=(count, height, cols), dtype=int64)
        obj.fill(0)
        return obj


class BarArray(BarsArray): ...


class RowArray(BarArray): ...


class ColArray(BarArray): ...


@final
class BidArray(ColArray): ...


@final
class AskArray(ColArray): ...


class ProfileArray(np.ndarray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(cls, shape=(2, rows), dtype=int64)
        obj.fill(0)
        return obj

    def padding(self, before: int, after: int) -> Self:
        return np.pad(self, pad_width=((before, after), (0, 0))).view(
            ProfileArray
        )  # pyright: ignore[reportReturnType]


@final
class VPArray(ProfileArray): ...


@final
class DPArray(ProfileArray): ...


@final
class BarsHeadersArray(np.ndarray):
    def __new__(cls, rows: int) -> Self:
        obj = super().__new__(
            cls, shape=(rows, c.BH_ConstantCount), dtype=int64
        )
        obj.fill(0)
        return obj

    def padding(self, after: int) -> Self:
        return np.pad(self, pad_width=((0, after), (0, 0))).view(
            BarsHeadersArray
        )  # pyright: ignore[reportReturnType]
