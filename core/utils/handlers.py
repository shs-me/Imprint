import json
import sys
import traceback
from datetime import datetime
from functools import wraps
from types import TracebackType

from .. import CorePath


def error_handler(set_status_code: bool = False):
    def decorator(func):
        @wraps(wrapped=func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                return result

            except KeyboardInterrupt:
                pass

            except Exception:
                dump_exception()
                if set_status_code and len(args) > 0:
                    args[0].__dict__.get("manager")._for_error_action()

        return wrapper

    return decorator


def dump_exception() -> None:
    exc_type, exc_value, exc_tb = sys.exc_info()
    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": exc_type.__name__ if exc_type is not None else exc_type,
        "message": str(exc_value),
        "traceback": traceback.format_exception(exc_type, exc_value, exc_tb),
        "locals": {},
    }
    tb: TracebackType | None = exc_tb
    if tb is not None:
        while tb.tb_next:
            tb = tb.tb_next

        for var, val in tb.tb_frame.f_locals.items():
            data["locals"][var] = (
                repr(val.__dict__) if hasattr(val, "__dict__") else repr(val)
            )

    with open(file=CorePath.exc_dump, mode="a", encoding="utf-8") as f:
        json.dump(obj=data, fp=f, ensure_ascii=False, indent=4)
        f.write("\n---\n")
