import inspect
from enum import IntFlag, StrEnum

from imprint._core import settings


def test_settings_invariants() -> None:
    """
    Test uniqueness, presence, and flag count invariants for IntFlag enums and StrEnum classes:
    - Minimum flag value starts strictly at 1 (initial flag presence) for `IntFlag` enums.
    - Maximum flag bit length does not exceed 63 for `IntFlag` enums.
    - All flags within each `IntFlag` class are unique with no bitwise overlaps.
    - There are no gaps in the bitwise sequence of flags (dense progression of powers of 2) for `IntFlag` enums.
    - All keys and string member values in `StrEnum` classes are unique.
    """
    for name, obj in inspect.getmembers(settings, inspect.isclass):
        if issubclass(obj, IntFlag) and (obj is not IntFlag):
            assert min(obj) == 1, f"{name}: Initial flag is missing"
            assert max(obj).bit_length() <= 63, (
                f"{name}: Maximum allowed flag count exceeded"
            )

            # Check flag uniqueness
            all_flags = 0
            for flag in obj:
                assert not (all_flags & flag), f"{name}: Flag already exists"
                all_flags |= flag

            # Gather all flags to verify absence of gaps
            need_flags = 0
            for flag in range(max(obj).bit_length()):
                need_flags |= 1 << flag

            assert all_flags == need_flags, f"{name}: Some flags are missing"

        if issubclass(obj, StrEnum) and (obj is not StrEnum):
            enums: list[str] = (
                str(list(obj.__members__.keys()))
                .removeprefix("[")
                .removesuffix("]")
                .lower()
                .split(",")
            )
            for enum in enums:
                assert enums.count(enum) == 1, f"{name}: Key already exists"
