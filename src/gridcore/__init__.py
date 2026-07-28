"""GridCore package entry point.

Exposes primary user-facing interfaces, configuration structures, and runtime modes
for the GridCore trading and footprint analysis engine.
"""

from . import typing
from ._core import constant
from ._core.engine.base.base_footprint_reader import FootprintReader
from ._setup import Analysis, RunMode, Timeframe, cfg, run

__all__ = [
    "constant",
    "typing",
    "cfg",
    "run",
    "RunMode",
    "Analysis",
    "Timeframe",
    "FootprintReader",
]
