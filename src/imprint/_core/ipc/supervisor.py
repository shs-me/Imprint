"""Process orchestration and supervisor decorator.

Provides a decorator to wrap worker process entry point functions,
automating shared memory allocations, dispatching manager bindings, and ensuring
correct process-level resource cleanup on exit.
"""

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from imprint._core.utils import error_handler

P = ParamSpec("P")
R = TypeVar("R")


def supervisor(is_main: bool = False):
    """Wrap worker process main functions with Dispatcher IPC initialization and cleanup.

    Manages the lifecycle of the `Dispatcher` for a process and coordinates SharedMemory block attachment or unlinking
    at termination.

    Parameters
    ----------
    is_main : bool, default=False
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

                dp.run_client(func)

                dp.shm_buf.release()
                dp.shm.close()
                if is_main:
                    dp.shm.unlink()

            run()

        return wrapper

    return decorator
