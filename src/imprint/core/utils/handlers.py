from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from imprint.core.settings import StatusCodes as scs
from imprint.core.utils.tools import dump_exception

P = ParamSpec("P")
R = TypeVar("R")


def error_handler(set_status_code: bool = False):
    def decorator(func: Callable[P, R]) -> Callable[P, R | None]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            try:
                return func(*args, **kwargs)
            except Exception:
                dump_exception()
                if set_status_code and args:
                    manager = getattr(args[0], "manager", None)
                    if manager and hasattr(manager, "set_proc_sc"):
                        manager.set_proc_sc(scs.ERROR, wait_main_task=False)

        return wrapper

    return decorator
