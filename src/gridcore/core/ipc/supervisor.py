import gc
from functools import wraps


def supervisor(is_main: bool = False):
    """Decorator wrapping worker process main functions with Dispatcher IPC initialization and cleanup.

    Args:
        is_main (bool): True if decorating main orchestrator process entry point.
    """

    def decorator(func):
        @wraps(wrapped=func)
        def wrapper(**kwargs) -> None:
            from .dispatcher import Dispatcher

            dp: Dispatcher = Dispatcher(is_main=is_main, **kwargs)
            try:
                gc.collect()
                gc.disable()
                dp.run_client(func)

            except Exception:
                pass

            finally:
                gc.collect()
                dp.shm_buf.release()
                dp.shm.close()
                if is_main:
                    dp.shm.unlink()

        return wrapper

    return decorator
