import gc
import inspect
from functools import wraps
from multiprocessing.shared_memory import SharedMemory

from core import configurations
from core.configurations import Configuration, ConfigurationSHMSegments
from core.utils.handlers import error_handler
from core.utils.monitoring.agent_manager import AgentManager
from core.utils.monitoring.main_manager import MainManager


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
            backtesting=kwargs.pop("backtesting"),
            mode=kwargs.pop("mode"),
            symbol=kwargs.pop("symbol"),
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
            kwargs["configs"][name] = obj = (
                kwargs.pop(name) if name in kwargs else obj()
            )
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
