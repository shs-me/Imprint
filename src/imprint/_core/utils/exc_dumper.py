import inspect
import json
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from types import TracebackType
from typing import Any, ParamSpec, TypeVar, cast, final, override

from imprint._core import constant as c
from imprint._core.types import DumpMSG


class DebugEncoder(json.JSONEncoder):
    """Custom JSON encoder handling set, range, datetime, and non-serializable objects."""

    @override
    def default(self, o: Any):
        if isinstance(o, (set, range)):
            return list(o)  # pyright: ignore[reportUnknownArgumentType]
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, "__dict__"):
            return f"Object: {type(o).__name__}"
        return f"<Non-serializable: {type(o).__name__}>"


@final
@dataclass(slots=True)
class DumpException:
    exc_type: type[BaseException] | None = field(default=None, init=False)
    exc_value: BaseException | None = field(default=None, init=False)
    exc_tb: TracebackType | None = field(default=None, init=False)
    dump_msg: DumpMSG = field(
        default_factory=lambda: {
            "timestamp": "",
            "type": "",
            "message": "",
            "traceback": [],
            "locals": {},
        },
        init=False,
    )

    def dump_exception(self) -> None:
        self._get_exc_info()
        self._create_dump_msg()
        try:
            with open(file=c.EXC_DUMP_PATH, mode="a", encoding="utf-8") as f:
                json.dump(
                    obj=self.dump_msg,
                    fp=f,
                    ensure_ascii=False,
                    indent=4,
                    cls=DebugEncoder,
                )
                f.write("\n" + "=" * 50 + "\n")

        except Exception as final_err:
            sys.stderr.write(
                f"Critical error during dump_exception: {final_err}\n"
            )

    def _get_exc_info(self) -> None:
        self.exc_type, self.exc_value, self.exc_tb = sys.exc_info()

    def _create_dump_msg(self) -> None:
        self.dump_msg["timestamp"] = datetime.now(tz=UTC).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.dump_msg["type"] = (
            self.exc_type.__name__ if self.exc_type else "UnknownError"
        )
        self.dump_msg["message"] = str(self.exc_value)
        self.dump_msg["traceback"] = traceback.format_exception(
            self.exc_type, self.exc_value, self.exc_tb
        )
        self.dump_msg["locals"] = {}

        if self.exc_tb:
            while self.exc_tb.tb_next:
                self.exc_tb = self.exc_tb.tb_next

            frame_locals: dict[str, Any] = self.exc_tb.tb_frame.f_locals
            for var_name, var_val in frame_locals.items():
                try:
                    self.dump_msg["locals"][var_name] = self._process_value(
                        var_val
                    )
                except Exception as e:
                    self.dump_msg["locals"][var_name] = (
                        f"<Error processing value: {e}>"
                    )

    def _process_value(self, val: Any, max_len: int = 100) -> Any:
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
            val = cast(list[Any] | tuple[Any] | set[Any], val)
            content = list(val)[:10]
            suffix = "..." if len(val) > 10 else ""
            return f"{type(val).__name__}(len={len(val)}): {content}{suffix}"

        if isinstance(val, dict):
            val = cast(dict[Any, Any], val)
            return {
                "__info__": f"dict(len={len(val)})",
                "keys": list(val.keys())[:20],
            }

        if isinstance(val, (str, bytes)):
            if len(val) > max_len:
                preview = val[:max_len]
                return f"{type(val).__name__}(len={len(val)}): {preview!r}..."
            return val

        if inspect.isfunction(val) or inspect.isclass(val):
            return f"<{type(val).__name__}: {val.__name__}>"

        if hasattr(val, "__dict__"):
            attrs: dict[Any, Any] = {}
            for k, v in val.__dict__.items():
                if not k.startswith("_"):
                    if isinstance(v, (int, float, str, bool, type(None))):
                        attrs[k] = v
                    else:
                        attrs[k] = f"<{type(v).__name__}>"

            val = cast(dict[Any, Any], val)
            return {"object": type(val).__name__, "attributes": attrs}

        return repr(val)


P = ParamSpec("P")
R = TypeVar("R")


def error_handler():
    def decorator(func: Callable[P, R]) -> Callable[P, R | None]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            dumper: DumpException = DumpException()
            try:
                return func(*args, **kwargs)
            except Exception:
                dumper.dump_exception()

        return wrapper

    return decorator
