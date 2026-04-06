import gc
import json
import sys
import traceback
from datetime import datetime
from functools import wraps
from multiprocessing.shared_memory import SharedMemory
from types import TracebackType

from ... import Config, ManagerAgent
from ... import ShmBufOffset as sbo


def error_action(set_sc: bool = False):
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
                if set_sc and len(args) > 0:
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
            data["locals"][var] = repr(val) if var != "self" else repr(val.__dict__)

    with open(file=Config.CorePath.exc_info, mode="a", encoding="utf-8") as f:
        json.dump(obj=data, fp=f, ensure_ascii=False, indent=4)
        f.write("\n---\n")


def manager_office(head_of_office: bool):
    def decorator(func):
        @wraps(wrapped=func)
        def wrapper(**kwargs) -> None:
            if (temp := _shm_init(head_of_office)) is None:
                return
            else:
                shm, shm_buf = temp
            try:
                gc.disable()

                @error_action()
                def run() -> None:
                    agent = _agent_init(buf=shm_buf, head=head_of_office, **kwargs)
                    func(manager=agent, **kwargs)

                run()

            finally:
                gc.collect()
                shm_buf.release()
                shm.close()
                if head_of_office:
                    shm.unlink()

        return wrapper

    return decorator


def _agent_init(buf, head: bool, **kwargs):
    if head:
        return buf

    agent: ManagerAgent = ManagerAgent(
        proc_id=kwargs["proc_id"],
        task_id=kwargs["task_id"],
        shm_buf=buf,
        sc_sem=kwargs["sc_sem"],
    )
    return agent


def _shm_init(create: bool) -> tuple[SharedMemory, memoryview] | None:
    if create:
        try:
            shm = SharedMemory(name=sbo.shm_name, size=sbo.shm_size, create=True)
        except FileExistsError:
            dump_exception()
            shm = SharedMemory(name=sbo.shm_name)

        if shm.buf is not None:
            shm_buf = shm.buf
            shm_buf[:] = b"\x00" * shm.size
            return shm, shm_buf

    else:
        try:
            shm = SharedMemory(name=sbo.shm_name)
            if shm.buf is not None:
                shm_buf = shm.buf
                return shm, shm_buf

        except FileNotFoundError:
            dump_exception()
