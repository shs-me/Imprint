"""Unit tests for `imprint._core.ipc`."""

from typing import Any

import pytest

from imprint._core.ipc.dispatcher import Dispatcher
from imprint._core.ipc.manager.host import Host as HostManager
from imprint._core.ipc.manager.node import Node as NodeManager
from imprint._core.settings import ProcsIds
from imprint._core.settings import StatusCodes as scs


@pytest.fixture
def ipc_setup() -> tuple[HostManager, NodeManager]:
    """Builds an in-memory memoryview buffer with initialized configurations."""
    kwg: dict[Any, Any] = {}
    dispatcher = Dispatcher(is_main=True, kwg=kwg)
    dispatcher.configurations_init()

    total_shm_size = kwg["Segments"]["ShmSize"]
    raw_buffer = bytearray(total_shm_size)
    shm_buf = memoryview(raw_buffer)

    host = HostManager(
        _segments=kwg["Segments"],
        _shm_buf=shm_buf,
        _configs=kwg["Configs"],
        _main_tools=kwg["MainTools"],
    )

    node = NodeManager(
        _proc_id=ProcsIds.engine,
        _task_id=ProcsIds.engine + 10,
        _segments=kwg["Segments"],
        _shm_buf=shm_buf,
        _configs=kwg["Configs"],
        _main_tools=kwg["MainTools"],
    )

    return host, node


class TestDispatcherLayout:
    def test_configurations_init_calculates_page_aligned_shm_size(self):
        kwg: dict[Any, Any] = {}
        dispatcher = Dispatcher(is_main=True, kwg=kwg)
        dispatcher.configurations_init()

        assert "ShmSize" in kwg["Segments"]
        assert kwg["Segments"]["ShmSize"] > 0
        assert kwg["Segments"]["ShmSize"] % 4096 == 0
        assert len(kwg["MainTools"]) == 2  # Event, Semaphore


class TestNodeAndHostMessaging:
    def test_node_writes_text_and_host_reads_it(
        self, ipc_setup: tuple[HostManager, NodeManager]
    ) -> None:
        host, node = ipc_setup

        node.set_log("Engine worker ready")
        assert node._procs_status[ProcsIds.engine] & scs.HAVE_LOG

        # Host reads messages from TextStream buffer
        messages = host.get_log(proc_id=ProcsIds.engine)
        assert len(messages) == 1
        timestamp, text = messages[0]
        assert timestamp > 0
        assert text == "Log: Engine worker ready"

    def test_node_set_proc_sc_signals_host(
        self, ipc_setup: tuple[HostManager, NodeManager]
    ) -> None:
        host, node = ipc_setup

        node.set_proc_sc(scs.FP_RE_INIT, wait_main_task=False)

        assert host._procs_status[ProcsIds.engine] & scs.FP_RE_INIT
        assert host._main_status[ProcsIds.engine] == 1
        assert host._sc_sem.get_value() == 1

    def test_node_status_check_and_gc_task(
        self, ipc_setup: tuple[HostManager, NodeManager]
    ) -> None:
        host, node = ipc_setup

        assert node.have_status() is False
        host.set_sc(node._task_id, scs.GC_COLLECT)

        assert node.have_status() is True
        task = node.check_base_task()
        assert task & scs.GC_COLLECT
        # Auto-cleared after execution
        assert (node._procs_status[node._task_id] & scs.GC_COLLECT) == 0

    def test_host_clear_proc_sc(
        self, ipc_setup: tuple[HostManager, NodeManager]
    ) -> None:
        host, node = ipc_setup

        node.set_proc_sc(scs.INVALID_DATA, wait_main_task=False)
        assert host._procs_status[ProcsIds.engine] & scs.INVALID_DATA

        host.clear_proc_sc(scs.INVALID_DATA, proc_id=ProcsIds.engine)
        assert (host._procs_status[ProcsIds.engine] & scs.INVALID_DATA) == 0
