from imprint._core import constant as c
from imprint._core import settings

PREFIX_MAP = {
    "BH_": settings.BarHeaders,
    "SF_": settings.StateFlags,
    "OB_": settings.OrderBook,
    "EH_": settings.EquityHeaders,
    "TP_": settings.TradeParam,
    "OF_": settings.OrderFlag,
    "RIF_": settings.ReInitFlag,
}


def test_constants_invariants():
    """
    Test strict bijection invariants between flat module constants and their corresponding Enum classes:
    - Count invariant: The total number of flat constants matching a prefix in `constant.py`
      must exactly equal the number of members in the mapped Enum class.
    - Value bijection invariant: Every constant value in `constant.py` must precisely
      match the integer value of its corresponding Enum member.
    """
    for prefix, enum_cls in PREFIX_MAP.items():
        enum_members: dict[str | None, int] = {m.name: int(m) for m in enum_cls}

        # Find all constants in constant.py with the given prefix
        module_constants: dict[str, int] = {}
        for attr in dir(c):
            if attr.startswith(prefix):
                clean_name: str = attr[len(prefix) :]
                module_constants[clean_name] = getattr(c, attr)

        # 1. Verify that the number of constants matches the number of Enum members
        assert len(module_constants) == len(enum_members), (
            f"Count mismatch for {prefix}: "
            f"Enum has {len(enum_members)}, constant.py has {len(module_constants)}. "
            f"Difference: {set(enum_members.keys()) ^ set(module_constants.keys())}"
        )

        # 2. Verify exact value matching
        for name, expected_val in enum_members.items():
            if (
                name is None
            ):  # Name can be missing only if a Flag is not declared within the class itself
                continue

            actual_val = module_constants.get(name)
            assert actual_val == expected_val, (
                f"Constant desynchronization {prefix}{name}: "
                f"Enum={expected_val}, Constant={actual_val}"
            )
