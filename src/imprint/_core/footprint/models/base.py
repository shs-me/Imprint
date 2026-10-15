from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field

from imprint._core.footprint.models.converter import Converter
from imprint._core.utils import FPArray
from imprint._core.utils.base import FPHeadersArray


@dataclass(slots=True)
class Chart(ABC):
    """Abstract base class representing a financial chart data structure."""

    con: Converter

    base: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)
    state: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)
    ctrade: FPArray = field(default_factory=lambda: FPArray(0, 0), init=False)
    headers: FPHeadersArray = field(
        default_factory=lambda: FPHeadersArray(0), init=False
    )
    headers_offset: memoryview = field(init=False)
