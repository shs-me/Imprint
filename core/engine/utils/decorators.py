import gc
import json
import sys
import traceback
from datetime import datetime
from functools import wraps
from multiprocessing.shared_memory import SharedMemory
from types import TracebackType

from ... import Config, ShMs


def error_action(set_sc_code=False, except_return: bool | None = None):
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
                if set_sc_code and len(args) > 0:
                    args[0].__dict__.get("_mo")._for_error_action()

            return except_return

        return wrapper

    return decorator


def dump_exception() -> None:
    exc_type, exc_value, exc_tb = sys.exc_info()
    data = {
        "timestamp": datetime.now().isoformat(),
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
            data["locals"][var] = repr(val) if var != "self" else repr(val.__dict__)

    with open(file=Config.CorePath.exc_info, mode="a", encoding="utf-8") as f:
        json.dump(obj=data, fp=f, ensure_ascii=False, indent=4)
        f.write("\n---\n")


def shm_manager(create: bool):
    def decorator(func):
        @wraps(wrapped=func)
        def wrapper(*args, **kwargs) -> None:
            if (temp := _shm_init(create)) is None:
                return
            else:
                shm, shm_buf = temp
            try:
                gc.disable()

                @error_action()
                def _() -> None:
                    func(*args, shm_buf=shm_buf, **kwargs)

                _()

            finally:
                shm_buf.release()
                shm.close()
                if create:
                    shm.unlink()
                gc.collect()

        return wrapper

    return decorator


def _shm_init(create: bool) -> tuple[SharedMemory, memoryview] | None:
    if create:
        try:
            shm = SharedMemory(name=ShMs.shm_name, size=ShMs.shm_size, create=True)
        except FileExistsError:
            dump_exception()
            shm = SharedMemory(name=ShMs.shm_name)

        if shm.buf is not None:
            shm_buf = shm.buf
            shm_buf[:] = b"\x00" * shm.size
            return shm, shm_buf

    else:
        try:
            shm = SharedMemory(name=ShMs.shm_name)
            if shm.buf is not None:
                shm_buf = shm.buf
                return shm, shm_buf

        except FileNotFoundError:
            dump_exception()
