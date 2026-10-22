"""Configure system Loguru logging sinks and output formatters for Imprint subsystems."""

import os
from collections.abc import Callable
from types import ModuleType
from typing import Any

from loguru import logger

import imprint._boot as _iboot
import imprint._core as _icore
import imprint._core.constant as c
import imprint._vis as _ivis


def _only_from(pkg: ModuleType) -> Callable[[Any], bool]:
    """Match records by the *file* they were emitted from, not by module name.

    Streamlit executes ``_vis/main.py`` as ``__main__``, so a name-based
    filter (``name.startswith("imprint._vis")``) silently drops every record
    logged from the script itself. The source path is stable in both cases.
    """
    root: str = os.path.normcase(os.path.abspath(list(pkg.__path__)[0]))

    def _filter(record: Any) -> bool:
        path: str = os.path.normcase(os.path.abspath(record["file"].path))
        return path == root or path.startswith(root + os.sep)

    return _filter


logger.remove()
logger.add(
    c.API_LOG_PATH,
    format="{time:YY:MM:DD-HH:mm:ss} | {level} | Imprint | {message}",
    filter=_only_from(_iboot),
    rotation="10 MB",
    colorize=True,
    enqueue=True,
)
logger.add(
    c.CORE_LOG_PATH,
    format=(
        "{elapsed} | {extra[time]} | {extra[level]} | {extra[proc_name]} | {message}"
    ),
    filter=_only_from(_icore),
    rotation="10 MB",
    colorize=True,
    enqueue=True,
)
logger.add(
    c.VISUALIZATION_LOG_PATH,
    format="{time:YY:MM:DD-HH:mm:ss} | {level} | {message}",
    filter=_only_from(_ivis),
    rotation="10 MB",
    colorize=True,
    enqueue=True,
)
