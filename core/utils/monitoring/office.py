import gc
import inspect
from functools import wraps
from multiprocessing.shared_memory import SharedMemory

from ... import Configuration, ConfigurationSHMSegments, configurations
from .. import error_handler
from . import AgentManager, MainManager


def manager_office(main: bool = False):
    def decorator(func):
        @wraps(wrapped=func)
        def wrapper(**kwargs) -> None:
            if main:
                if (kwargs := configurations_init(**kwargs)) is None:
                    return
                else:
                    if (
                        temp := shm_init(
                            create=True, size=kwargs["segments"].pop("shm_size")
                        )
                    ) is None:
                        return
                    else:
                        shm, shm_buf = temp
            else:
                if (temp := shm_init(create=False)) is None:
                    return
                else:
                    shm, shm_buf = temp
            try:
                gc.disable()

                @error_handler()
                def run() -> None:
                    manager = agent_init(main=main, shm_buf=shm_buf, **kwargs)
                    func(manager=manager, **kwargs)

                run()

            finally:
                gc.collect()
                shm_buf.release()
                shm.close()
                if main:
                    shm.unlink()

        return wrapper

    return decorator


def agent_init(main: bool, shm_buf: memoryview, **kwargs):
    if main:
        manager = MainManager(
            segments=kwargs["segments"],
            configs=kwargs["configs"],
            shm_buf=shm_buf,
        )
    else:
        manager = AgentManager(
            proc_id=kwargs.pop("proc_id"),
            task_id=kwargs.pop("task_id"),
            segments=kwargs.pop("segments"),
            configs=kwargs.pop("configs"),
            shm_buf=shm_buf,
            sc_sem=kwargs.pop("sc_sem"),
        )
    return manager


@error_handler()
def configurations_init(**kwargs) -> dict:
    offset = 0
    kwargs["configs"], kwargs["segments"] = {}, {}
    kwargs["configs"]["subclasses"], kwargs["segments"]["subclasses"] = [], []
    for name, obj in inspect.getmembers(configurations, inspect.isclass):
        if (
            issubclass(obj, Configuration)
            and obj is not Configuration
            and obj is not ConfigurationSHMSegments
        ):
            if name in kwargs:
                obj = kwargs["configs"][name]

            if isinstance(obj, obj) is False:
                kwargs["configs"][name] = obj = obj()

            kwargs["configs"]["subclasses"].append(name)
            if issubclass(obj.__class__, ConfigurationSHMSegments):
                kwargs["segments"][name] = slice(
                    offset, (offset := (offset + obj.shm_size))
                )
                kwargs["segments"]["subclasses"].append(name)

    kwargs["segments"]["shm_size"] = offset
    return kwargs


@error_handler()
def shm_init(
    create: bool, size: int = 0, name: str = "GridCore"
) -> tuple[SharedMemory, memoryview] | None:
    if create:
        shm = SharedMemory(name=name, size=size, create=True)
        if shm.buf is not None:
            shm_buf = shm.buf
            shm_buf[:] = b"\x00" * shm.size
            return shm, shm_buf

    else:
        shm = SharedMemory(name=name)
        if shm.buf is not None:
            shm_buf = shm.buf
            return shm, shm_buf
