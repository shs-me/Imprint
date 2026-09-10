"""Unit tests for `imprint.core.utils.handlers`."""

from unittest.mock import MagicMock

import pytest

from imprint._core.ipc import NodeManager
from imprint._core.settings import StatusCodes as scs
from imprint._core.utils.handlers import error_handler


class TestErrorHandler:
    def test_successful_execution_returns_result(self) -> None:
        @error_handler()
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_exception_caught_and_dumped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_dump = MagicMock()
        monkeypatch.setattr(
            "imprint.core.utils.handlers.dump_exception", mock_dump
        )

        @error_handler()
        def faulty() -> None:
            raise ValueError("Something broke")

        result = faulty()
        assert result is None
        mock_dump.assert_called_once()

    def test_set_status_code_when_manager_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_dump = MagicMock()
        monkeypatch.setattr(
            "imprint.core.utils.handlers.dump_exception", mock_dump
        )

        mock_manager = MagicMock()

        class Worker:
            def __init__(self) -> None:
                self.manager: NodeManager = mock_manager

            @error_handler(set_status_code=True)
            def run(self) -> None:
                raise RuntimeError("Crash inside worker")

        worker = Worker()
        worker.run()

        mock_dump.assert_called_once()
        mock_manager.set_proc_sc.assert_called_once_with(
            scs.ERROR, wait_main_task=False
        )

    def test_set_status_code_without_manager_or_args_does_not_fail(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_dump = MagicMock()
        monkeypatch.setattr(
            "imprint.core.utils.handlers.dump_exception", mock_dump
        )

        @error_handler(set_status_code=True)
        def standalone() -> None:
            raise ZeroDivisionError("division by zero")

        standalone()
        mock_dump.assert_called_once()
