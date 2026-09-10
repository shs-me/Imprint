import gc
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from imprint._core.utils import error_handler

P = ParamSpec("P")
R = TypeVar("R")


def supervisor(is_main: bool = False):
    """Decorator wrapping worker process main functions with Dispatcher IPC initialization and cleanup.

    Args:
        is_main (bool): True if decorating main orchestrator process entry point.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R | None]:
        @wraps(wrapped=func)
        def wrapper(*_args: P.args, **kwargs: P.kwargs) -> R | None:
            @error_handler()
            def run() -> None:
                from imprint._core.ipc.dispatcher import Dispatcher

                dp: Dispatcher = Dispatcher(is_main=is_main, kwg=kwargs)

                gc.collect()
                gc.disable()

                dp.run_client(func)

                gc.collect()

                dp.shm_buf.release()
                dp.shm.close()
                if is_main:
                    dp.shm.unlink()

            run()

        return wrapper

    return decorator
