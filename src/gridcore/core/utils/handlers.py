from functools import wraps

from ..settings import StatusCodes as scs
from .tools import dump_exception


def error_handler(set_status_code: bool = False):
    """Decorator capturing uncaught exceptions, writing crash dumps, and updating process status.

    Args:
        set_status_code (bool): Flag to automatically report scs.ERROR status code to manager.
    """

    def decorator(func):
        @wraps(wrapped=func)
        def wrapper(*args, **kwargs):
            def set_sc(set_status_code: bool, args: tuple, code: scs) -> None:
                if set_status_code and args:
                    manager = getattr(args[0], "manager", None)
                    if manager and hasattr(manager, "set_proc_sc"):
                        manager.set_proc_sc(code, wait_main_task=False)

            try:
                return func(*args, **kwargs)

            except Exception:
                dump_exception()
                set_sc(set_status_code, args, scs.ERROR)

        return wrapper

    return decorator
