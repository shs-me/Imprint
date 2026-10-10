"""Configure system Loguru logging sinks and output formatters for Imprint subsystems."""

from loguru import logger

import imprint._boot as _iboot
import imprint._core as _icore
import imprint._vis as _ivis
from imprint._core import constant as c

logger.remove()
logger.add(
    c.API_LOG_PATH,
    format="{time:YY:MM:DD-HH:mm:ss} | {level} | Imprint | {message}",
    filter=lambda r: r["name"].startswith(_iboot.__name__),  # pyright: ignore[reportOptionalMemberAccess]
    rotation="10 MB",
    colorize=True,
    enqueue=True,
)
logger.add(
    c.CORE_LOG_PATH,
    format=(
        "{elapsed} | {extra[time]} | {extra[level]} | {extra[proc_name]} | {message}"
    ),
    filter=lambda r: r["name"].startswith(_icore.__name__),  # pyright: ignore[reportOptionalMemberAccess]
    rotation="10 MB",
    colorize=True,
    enqueue=True,
)
logger.add(
    c.VISUALIZATION_LOG_PATH,
    format="{time:YY:MM:DD-HH:mm:ss} | {level} | {message}",
    filter=lambda r: r["name"].startswith(_ivis.__name__),  # pyright: ignore[reportOptionalMemberAccess]
    rotation="10 MB",
    colorize=True,
    enqueue=True,
)
