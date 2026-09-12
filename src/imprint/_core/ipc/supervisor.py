"""Module providing process orchestration and supervisor decorator.

This module contains a decorator to wrap worker process entry point functions,
automating shared memory allocations, dispatching manager bindings, and ensuring
correct process-level resource cleanup on exit.
"""

import gc
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from imprint._core.utils import error_handler

P = ParamSpec("P")
R = TypeVar("R")


def supervisor(is_main: bool = False):
    """Decorator wrapping worker process main functions with Dispatcher IPC initialization and cleanup.

    This decorator manages the lifecycle of the `Dispatcher` for a process, handles
    garbage collection cycles, and coordinates SharedMemory block attachment or unlinking
    at termination.

    Parameters
    ----------
    is_main : bool, default False
        True if decorating the main orchestrator/host process entry point. If True,
        responsible for configuration scanning, SharedMemory allocation, and
        final segment unlinking.

    Returns
    -------
    Callable[[Callable[P, R]], Callable[P, R | None]]
        A wrapper decorator that injects IPC setups, executes the target function
        via the Dispatcher, and gracefully cleans up resources.
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
