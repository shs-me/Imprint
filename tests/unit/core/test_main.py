"""Unit tests for `imprint._core.main.MainAgent`."""

from multiprocessing.synchronize import Event, Semaphore
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from imprint._core.configs import Setup
from imprint._core.main import MainAgent
from imprint._core.settings import LogLevel, ProcsIds


@pytest.fixture
def mock_host_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.cfgSetup = Setup(backtesting=True, execution=True)
    return mgr


class TestMainAgent:
    def test_initialization(self, mock_host_manager: MagicMock) -> None:
        agent = MainAgent(manager=mock_host_manager, base_kwargs={"foo": "bar"})
        assert agent.is_backtesting is True
        assert agent.with_execution is True
        assert isinstance(agent.wss_sem, Semaphore)
        assert isinstance(agent.engine_event, Event)
        assert isinstance(agent.execution_event, Event)

    def test_check_dirs_creates_directories(
        self,
        mock_host_manager: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        d1 = tmp_path / "data"
        d2 = tmp_path / "logs"
        monkeypatch.setattr("imprint._core.main.DIRS_LIST", [str(d1), str(d2)])

        agent = MainAgent(manager=mock_host_manager, base_kwargs={})
        agent.check_dirs()

        assert d1.exists()
        assert d2.exists()

    def test_get_procs_funcs_with_and_without_execution(
        self, mock_host_manager: MagicMock
    ) -> None:
        # 1. With execution -> 3 processes
        agent = MainAgent(manager=mock_host_manager, base_kwargs={})
        funcs = agent.get_procs_funcs()
        assert len(funcs) == 3
        ids = [p_id for _, p_id in funcs]
        assert ids == [ProcsIds.streaming, ProcsIds.engine, ProcsIds.executing]

        # 2. Without execution -> 2 processes
        mock_host_manager.cfgSetup.execution = False
        agent_no_exec = MainAgent(manager=mock_host_manager, base_kwargs={})
        funcs_no_exec = agent_no_exec.get_procs_funcs()
        assert len(funcs_no_exec) == 2
        ids_no_exec = [p_id for _, p_id in funcs_no_exec]
        assert ids_no_exec == [ProcsIds.streaming, ProcsIds.engine]

    def test_get_kwargs_for_func_resolves_signature(
        self, mock_host_manager: MagicMock
    ) -> None:
        agent = MainAgent(
            manager=mock_host_manager, base_kwargs={"custom_param": 123}
        )

        def dummy_streaming_proc(
            engine_event: ..., wss_sem: ..., **kwargs: ...
        ) -> None: ...

        kwargs = agent.get_kwargs_for_func(
            dummy_streaming_proc, proc_id=0, task_id=10
        )
        assert kwargs is not None
        assert kwargs["engine_event"] is agent.engine_event
        assert kwargs["wss_sem"] is agent.wss_sem
        assert kwargs["proc_id"] == 0
        assert kwargs["task_id"] == 10
        assert kwargs["custom_param"] == 123

    def test_get_kwargs_for_func_missing_param_returns_none(
        self, mock_host_manager: MagicMock
    ) -> None:
        agent = MainAgent(manager=mock_host_manager, base_kwargs={})

        def invalid_proc(_non_existent_arg: ...): ...

        result = agent.get_kwargs_for_func(invalid_proc, proc_id=0, task_id=10)
        assert result is None
        mock_host_manager.logger.assert_called_with(
            "Missing arg: [non_existent_arg] for [Invalid]", LogLevel.ERROR
        )

    def test_run_procs_flow_with_mocked_process(
        self, mock_host_manager: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_process_cls = MagicMock()
        monkeypatch.setattr("imprint._core.main.Process", mock_process_cls)

        agent = MainAgent(manager=mock_host_manager, base_kwargs={})
        success = agent.run_procs()

        assert success is True
        # Called general_event(False) then general_event(True)
        assert mock_host_manager.general_event.call_count == 2
        assert mock_process_cls.call_count == 3  # 3 processes created
