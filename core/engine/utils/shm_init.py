import traceback
from contextlib import ContextDecorator
from multiprocessing.shared_memory import SharedMemory

from ... import ShMs


class ShMControl(ContextDecorator):
    def __init__(self, create=False) -> None:
        self.create = create


def shm_load() -> tuple[SharedMemory, memoryview] | None:
    try:
        shm = SharedMemory(name=ShMs.shm_name)
        if shm.buf is not None:
            shm_buf = shm.buf

            return shm, shm_buf

    except FileNotFoundError:
        traceback.print_exc()
