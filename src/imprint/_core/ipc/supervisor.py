"""Provide worker process entry point supervision and IPC lifecycle management."""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from imprint._core.utils import error_handler

P = ParamSpec("P")
R = TypeVar("R")


def supervisor(is_main: bool = False):
    """Wrap worker process entry point functions with IPC resource allocation and cleanup.

    Manages the lifecycle of the process ``Dispatcher``, coordinates shared memory block
    allocation or attachment, and guarantees proper resource release or unlinking
    upon process exit.

    Parameters
    ----------
    is_main : bool, default=False
        Flag indicating whether the decorated function is the host process entry point.
        If True, allocates and unlinks shared memory; if False, attaches to existing memory.

    Returns
    -------
    Callable[[Callable[P, R]], Callable[P, R | None]]
        Decorator that instantiates the Dispatcher and executes the target entry point.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R | None]:
        @wraps(wrapped=func)
        def wrapper(*_args: P.args, **kwargs: P.kwargs) -> R | None:
            @error_handler()
            def run() -> None:
                from imprint._core.ipc.dispatcher import Dispatcher

                dp: Dispatcher = Dispatcher(is_main=is_main, kwg=kwargs)

                dp.run_client(func)

                dp.shm_buf.release()
                dp.shm.close()
                if is_main:
                    dp.shm.unlink()

            run()

        return wrapper

    return decorator
