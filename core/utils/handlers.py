import inspect
import json
import sys
import traceback
from datetime import datetime
from functools import wraps
from types import TracebackType
from typing import Any

from core.constant import EXC_DUMP_PATH


class DebugEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (set, range)):
            return list(o)
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, "__dict__"):
            return f"Object: {type(o).__name__}"
        return f"<Non-serializable: {type(o).__name__}>"


def process_value(val: Any, max_len: int = 100) -> Any:
    if isinstance(val, memoryview):
        return {
            "type": "memoryview",
            "format": val.format,
            "shape": val.shape,
            "nbytes": val.nbytes,
            "readonly": val.readonly,
            "obj_type": type(val.obj).__name__,
        }

    if isinstance(val, (list, tuple, set)):
        content = list(val)[:10]
        suffix = "..." if len(val) > 10 else ""
        return f"{type(val).__name__}(len={len(val)}): {content}{suffix}"

    if isinstance(val, dict):
        return {"__info__": f"dict(len={len(val)})", "keys": list(val.keys())[:20]}

    if isinstance(val, (str, bytes)):
        if len(val) > max_len:
            preview = val[:max_len]
            return f"{type(val).__name__}(len={len(val)}): {preview!r}..."
        return val

    if inspect.isfunction(val) or inspect.isclass(val):
        return f"<{type(val).__name__}: {val.__name__}>"

    if hasattr(val, "__dict__"):
        attrs = {}
        for k, v in val.__dict__.items():
            if not k.startswith("_"):
                if isinstance(v, (int, float, str, bool, type(None))):
                    attrs[k] = v
                else:
                    attrs[k] = f"<{type(v).__name__}>"
        return {"object": type(val).__name__, "attributes": attrs}

    return repr(val)


def error_handler(set_status_code: bool = False):
    def decorator(func):
        @wraps(wrapped=func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                pass
            except Exception:
                dump_exception()
                if set_status_code and args:
                    manager = getattr(args[0], "manager", None)
                    if manager and hasattr(manager, "_for_error_action"):
                        manager._for_error_action()

        return wrapper

    return decorator


def dump_exception() -> None:
    exc_type, exc_value, exc_tb = sys.exc_info()

    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": exc_type.__name__ if exc_type else "UnknownError",
        "message": str(exc_value),
        "traceback": traceback.format_exception(exc_type, exc_value, exc_tb),
        "locals": {},
    }

    tb: TracebackType | None = exc_tb
    if tb:
        while tb.tb_next:
            tb = tb.tb_next

        frame_locals = tb.tb_frame.f_locals
        for var_name, var_val in frame_locals.items():
            try:
                data["locals"][var_name] = process_value(var_val)
            except Exception as e:
                data["locals"][var_name] = f"<Error processing value: {e}>"

    try:
        with open(file=EXC_DUMP_PATH, mode="a", encoding="utf-8") as f:
            json.dump(obj=data, fp=f, ensure_ascii=False, indent=4, cls=DebugEncoder)
            f.write("\n" + "=" * 50 + "\n")

    except Exception as final_err:
        sys.stderr.write(f"Critical error during dump_exception: {final_err}\n")
