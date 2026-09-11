"""Unit tests for `imprint._core.settings`."""

import pytest

from imprint._core.settings import (
    BarHeaders,
    CachedStatesData,
    EquityHeaders,
    KwgsKeys,
    LogLevel,
    OrderBook,
    OrderFlag,
    ProcsIds,
    StateFlags,
    StatusCodes,
    Timeframe,
    TradeParam,
)


class TestProcsIds:
    def test_values_start_at_zero_and_increment(self) -> None:
        assert ProcsIds.streaming == 0
        assert ProcsIds.engine == 1
        assert ProcsIds.executing == 2


class TestKwgsKeys:
    def test_all_members_unique(self) -> None:
        values = [member.value for member in KwgsKeys]
        assert len(values) == len(set(values))


class TestLogLevel:
    def test_ordering(self) -> None:
        assert LogLevel.INFO < LogLevel.SUCCESS < LogLevel.WARNING
        assert LogLevel.WARNING < LogLevel.ERROR < LogLevel.CRITICAL


class TestStatusCodes:
    def test_first_member_is_single_bit(self) -> None:
        first = next(iter(StatusCodes))
        assert first.value == 1

    def test_each_member_is_a_single_bit_power_of_two(self) -> None:
        for member in StatusCodes:
            assert member.value > 0
            assert (member.value & (member.value - 1)) == 0

    def test_members_are_all_distinct_bits(self) -> None:
        combined = 0
        for member in StatusCodes:
            assert combined & member.value == 0
            combined |= member.value

    def test_value_matches_bit_position_order_of_definition(self) -> None:
        members = list(StatusCodes)
        for position, member in enumerate(members):
            assert member.value == (1 << position)

    def test_stays_under_64_members(self) -> None:
        assert len(StatusCodes.__members__) < 64


class TestStateFlags:
    def test_members_are_independent_bits(self) -> None:
        combined = StateFlags(0)
        for member in StateFlags:
            assert not (combined & member)
            combined |= member

    def test_combining_flags_is_bitwise_or(self) -> None:
        combo = StateFlags.OPEN | StateFlags.CLOSE
        assert bool(combo & StateFlags.OPEN)
        assert bool(combo & StateFlags.CLOSE)
        assert not (combo & StateFlags.HIGH)


class TestOrderFlag:
    def test_long_short_are_distinct_bits(self) -> None:
        assert OrderFlag.LONG != OrderFlag.SHORT
        assert not (OrderFlag.LONG & OrderFlag.SHORT)

    def test_composing_an_order_param(self) -> None:
        order_param = (
            OrderFlag.LONG | OrderFlag.SELL | OrderFlag.LIMIT | OrderFlag.NEW
        )
        assert bool(order_param & OrderFlag.LONG)
        assert bool(order_param & OrderFlag.SELL)
        assert not bool(order_param & OrderFlag.SHORT)
        assert not bool(order_param & OrderFlag.BUY)


class TestTimeframe:
    @pytest.mark.parametrize(
        "member,expected_ms",
        [
            (Timeframe.S30, 30_000),
            (Timeframe.M1, 60_000),
            (Timeframe.M5, 300_000),
            (Timeframe.M15, 900_000),
            (Timeframe.M30, 1_800_000),
            (Timeframe.H1, 3_600_000),
        ],
    )
    def test_millisecond_values(
        self, member: Timeframe, expected_ms: int
    ) -> None:
        assert int(member) == expected_ms

    def test_strictly_increasing(self) -> None:
        members = list(Timeframe)
        assert members == sorted(members)


@pytest.mark.parametrize(
    "enum_cls",
    [CachedStatesData, OrderBook, EquityHeaders, TradeParam, BarHeaders],
)
class TestContinuousUniqueIndexEnums:
    def test_values_are_zero_based_continuous_range(
        self,
        enum_cls: type[
            CachedStatesData
            | OrderBook
            | EquityHeaders
            | TradeParam
            | BarHeaders,
        ],
    ) -> None:
        values = sorted(member.value for member in enum_cls)
        assert values == list(range(len(enum_cls)))

    def test_constant_count_equals_member_count_minus_one(
        self,
        enum_cls: type[
            CachedStatesData
            | OrderBook
            | EquityHeaders
            | TradeParam
            | BarHeaders,
        ],
    ) -> None:
        assert enum_cls.ConstantCount.value == len(enum_cls) - 1
