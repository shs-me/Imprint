"""Unit tests for `imprint.core.utils.tools`."""

import io
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from imprint._core.utils.tools import (
    DebugEncoder,
    download_agg_trades_history,
    download_file,
    dump_exception,
    process_value,
    to_date,
)


class TestToDate:
    def test_converts_iso_strings_to_date_objects(self) -> None:
        result = to_date(["2026-01-01", "2026-06-15"])
        assert result == [date(2026, 1, 1), date(2026, 6, 15)]

    def test_empty_list_returns_empty_list(self) -> None:
        assert to_date([]) == []


class TestDebugEncoderDefault:
    @pytest.fixture(autouse=True)
    def setup_method(self) -> None:
        self.encoder: DebugEncoder = DebugEncoder()  # pyright: ignore[reportUninitializedInstanceVariable]

    def test_set_is_converted_to_list(self) -> None:
        result = self.encoder.default({1, 2, 3})
        assert isinstance(result, list)
        assert sorted(result) == [1, 2, 3]

    def test_range_is_converted_to_list(self) -> None:
        assert self.encoder.default(range(3)) == [0, 1, 2]

    def test_datetime_is_converted_to_isoformat_string(self) -> None:
        dt = datetime(2026, 1, 1, 12, 30, 0, tzinfo=UTC)
        assert self.encoder.default(dt) == dt.isoformat()

    def test_object_with_dict_falls_back_to_type_name_label(self) -> None:
        @dataclass
        class Widget:
            x: int = 1

        result = self.encoder.default(Widget())
        assert result == "Object: Widget"

    def test_object_without_dict_falls_back_to_non_serializable_label(
        self,
    ) -> None:
        result = self.encoder.default(1 + 2j)
        assert result == "<Non-serializable: complex>"

    def test_full_json_dumps_roundtrip_with_mixed_types(self) -> None:
        payload = {"a_set": {1, 2}, "a_range": range(2)}
        dumped = json.dumps(payload, cls=DebugEncoder)
        reloaded = json.loads(dumped)
        assert sorted(reloaded["a_set"]) == [1, 2]
        assert reloaded["a_range"] == [0, 1]


class TestProcessValue:
    def test_memoryview_reports_metadata(self) -> None:
        mv_rw = memoryview(bytearray(16)).cast("q")
        res_rw = process_value(mv_rw)
        assert res_rw["type"] == "memoryview"
        assert res_rw["nbytes"] == 16
        assert res_rw["readonly"] is False

        mv_ro = memoryview(b"12345678")
        res_ro = process_value(mv_ro)
        assert res_ro["readonly"] is True

    def test_short_and_long_sequences(self) -> None:
        # Short list/tuple/set
        assert process_value([1, 2, 3]) == "list(len=3) -> None: [1, 2, 3]"
        assert process_value((1, 2)) == "tuple(len=2) -> None: [1, 2]"
        # Long sequence > 10 items
        res_long = process_value(list(range(15)))
        assert res_long.startswith("list(len=15) -> None: ")
        assert res_long.endswith("...")
        assert str(list(range(10))) in res_long

    def test_dict_reports_length_and_first_20_keys(self) -> None:
        payload = {f"k{i}": i for i in range(25)}
        result = process_value(payload)
        assert result["__info__"] == "dict(len=25)"
        assert len(result["keys"]) == 20

    def test_strings_and_bytes(self) -> None:
        # Short string & bytes
        assert process_value("hello") == "hello"
        assert process_value(b"hello") == b"hello"
        # Long string & bytes
        long_str = "x" * 150
        res_str = process_value(long_str, max_len=100)
        assert res_str.startswith("str(len=150) -> None: ")
        assert "..." in res_str

        long_bytes = b"y" * 150
        res_bytes = process_value(long_bytes, max_len=100)
        assert res_bytes.startswith("bytes(len=150) -> None: ")
        assert "..." in res_bytes

    def test_function_is_summarized_by_name(self) -> None:
        def my_func() -> None:
            pass

        assert process_value(my_func) == "<function: my_func>"

    def test_class_is_summarized_by_name(self) -> None:
        class MyClass: ...

        assert process_value(MyClass) == "<class: MyClass>"

    def test_object_with_dict_reports_public_scalar_attrs(self) -> None:
        @dataclass
        class Position:
            qty: int = 10
            price: float = 100.5
            is_active: bool = True
            empty: None = None
            symbol: str = "BTCUSDT"
            _private: str = "hidden"
            nested: object = object()

        result = process_value(Position())
        assert result["object"] == "Position"
        assert result["attributes"]["qty"] == 10
        assert result["attributes"]["price"] == 100.5
        assert result["attributes"]["is_active"] is True
        assert result["attributes"]["empty"] is None
        assert result["attributes"]["symbol"] == "BTCUSDT"
        assert "_private" not in result["attributes"]
        assert result["attributes"]["nested"] == "<object>"

    def test_fallback_uses_repr_for_unhandled_scalar_types(self) -> None:
        assert process_value(3.14) == repr(3.14)
        assert process_value(None) == repr(None)


class TestDumpException:
    def test_writes_valid_json_entry_to_exc_dump_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import imprint._core.constant as const

        dump_path = tmp_path / "dump" / "exc_dump.json"
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(const, "EXC_DUMP_PATH", str(dump_path))

        try:
            _val = 42
            raise ValueError("boom")
        except ValueError:
            dump_exception()

        contents = dump_path.read_text(encoding="utf-8")
        assert "boom" in contents
        assert "ValueError" in contents

        json_part = contents.split("\n" + "=" * 50)[0]
        parsed = json.loads(json_part)
        assert parsed["type"] == "ValueError"
        assert parsed["message"] == "boom"
        assert "_val" in parsed["locals"]

    def test_dump_exception_when_no_active_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import imprint._core.constant as const

        dump_path = tmp_path / "dump" / "exc_dump.json"
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(const, "EXC_DUMP_PATH", str(dump_path))

        dump_exception()
        contents = dump_path.read_text(encoding="utf-8")
        assert "UnknownError" in contents

    def test_dump_exception_handles_file_write_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        import imprint._core.constant as const

        # Point to invalid dir path that cannot be written to
        monkeypatch.setattr(
            const, "EXC_DUMP_PATH", "/non_existent_dir/impossible/dump.json"
        )

        try:
            raise RuntimeError("fail")
        except RuntimeError:
            dump_exception()

        captured = capsys.readouterr()
        assert "Critical error during dump_exception:" in captured.err

    def test_dump_exception_handles_unserializable_local_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import imprint._core.constant as const
        import imprint._core.utils.tools as tools_mod

        dump_path = tmp_path / "dump" / "exc_dump.json"
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(const, "EXC_DUMP_PATH", str(dump_path))

        def buggy_process_value(_v: ...) -> None:
            raise ValueError("Cannot process")

        monkeypatch.setattr(tools_mod, "process_value", buggy_process_value)

        try:
            _x = 10
            raise TypeError("test error")
        except TypeError:
            dump_exception()

        contents = dump_path.read_text(encoding="utf-8")
        assert "<Error processing value: Cannot process>" in contents


class TestDownloadFile:
    def test_download_file_streams_chunks_with_content_length(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import urllib.request

        payload = b"Hello, trading engine! Download completed."

        class FakeResponse(io.BytesIO):
            def getheader(self, name: str) -> None | str:
                if name.lower() == "content-length":
                    return str(len(payload))
                return None

        fake_resp = FakeResponse(payload)
        monkeypatch.setattr(urllib.request, "urlopen", lambda url: fake_resp)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

        out_path = tmp_path / "downloaded.zip"
        download_file("http://fake.url/file.zip", str(out_path))

        assert out_path.read_bytes() == payload

    def test_download_file_without_content_length(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import urllib.request

        payload = b"Stream without length header."

        class FakeResponse(io.BytesIO):
            def getheader(self, _name: ...) -> None:
                return None

        fake_resp = FakeResponse(payload)
        monkeypatch.setattr(urllib.request, "urlopen", lambda url: fake_resp)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

        out_path = tmp_path / "downloaded_no_len.zip"
        download_file("http://fake.url/file.zip", str(out_path))

        assert out_path.read_bytes() == payload


class TestDownloadAggTradesHistory:
    def test_download_agg_trades_history_all_branches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import imprint._core.constant as const

        data_dir = tmp_path / "data"
        monkeypatch.setattr(const, "DATA_PATH", str(data_dir))
        monkeypatch.setattr(const, "DATA_TYPE_AGGTRADES_PATH", "aggTrades")

        # Mock download_file to create a valid zip file containing CSV
        csv_content = (
            "agg_trade_id,price,qty,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n"
            "1,100.5,2.0,1,1,1700000000000,True\n"
            "2,101.0,1.5,2,2,1700000001000,False\n"
        )

        def fake_download_file(_url: ..., _path: ...) -> None:
            with zipfile.ZipFile(_path, "w") as zf:
                zf.writestr("trade_data.csv", csv_content)

        import imprint._core.utils.tools as tools_mod

        monkeypatch.setattr(tools_mod, "download_file", fake_download_file)

        # 1. First run: Downloads zip, extracts to CSV, converts to NPY
        start_d = date(2026, 1, 1)
        end_d = date(2026, 1, 1)
        success = download_agg_trades_history(
            symbol="DASHUSDT",
            start_date=start_d,
            end_date=end_d,
            price_mult=100,
            qty_mult=1_000,
        )
        assert success is True

        symbol_dir = data_dir / "aggTrades" / "DASHUSDT"
        npy_path = symbol_dir / "2026-01-01.npy"
        assert npy_path.exists()

        arr = np.load(str(npy_path))
        assert arr.shape == (2, 4)
        assert arr[0, 0] == round(100.5 * 100)  # price
        assert arr[0, 1] == round(2.0 * 1_000)  # qty
        assert arr[0, 2] == 1700000000000  # timestamp
        assert arr[0, 3] == 1  # is_buyer_maker True -> 1

        # 2. Second run: NPY already exists -> skips downloading and processing
        download_agg_trades_history(
            symbol="DASHUSDT",
            start_date=start_d,
            end_date=end_d,
            price_mult=100,
            qty_mult=1_000,
        )

        # 3. Third run: CSV exists but NPY does not -> converts CSV to NPY without download
        os.remove(str(npy_path))
        csv_path = symbol_dir / "2026-01-01.csv"
        csv_path.write_text(csv_content, encoding="utf-8")

        mock_download = MagicMock()
        monkeypatch.setattr(tools_mod, "download_file", mock_download)

        download_agg_trades_history(
            symbol="DASHUSDT",
            start_date=start_d,
            end_date=end_d,
            price_mult=100,
            qty_mult=1_000,
        )
        assert mock_download.call_count == 0  # no download needed
        assert npy_path.exists()

        # 4. Fourth branch: end_date >= today -> capped to yesterday
        future_date = datetime.now(tz=UTC).date()
        # Should not raise, executes gracefully
        download_agg_trades_history(
            symbol="DASHUSDT",
            start_date=future_date,
            end_date=future_date,
            price_mult=100,
            qty_mult=1_000,
        )
