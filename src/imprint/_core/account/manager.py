from dataclasses import dataclass, field

from imprint._core import constant as c
from imprint._core.account.risk_management import RiskManagement
from imprint._core.settings import PositionFSM


@dataclass(slots=True)
class Manager(RiskManagement):
    __long_fsm: PositionFSM = field(
        default_factory=lambda: PositionFSM.EMPTY, init=False
    )
    __short_fsm: PositionFSM = field(
        default_factory=lambda: PositionFSM.EMPTY, init=False
    )
    __all_states: PositionFSM = field(
        default_factory=lambda: (
            PositionFSM.PENDING | PositionFSM.OPEN | PositionFSM.CLOSE
        ),
        init=False,
    )

    @property
    def long(self) -> PositionFSM:
        return self.__long_fsm

    @long.setter
    def long(self, state: PositionFSM) -> None:
        if state == PositionFSM.EMPTY:
            self.__long_fsm = state
        else:
            self.__long_fsm &= ~(PositionFSM.EMPTY)
            self.__long_fsm |= state

        if self.__long_fsm & self.__all_states == self.__all_states:
            self.__long_fsm = PositionFSM.EMPTY

    @property
    def short(self) -> PositionFSM:
        return self.__short_fsm

    @short.setter
    def short(self, state: PositionFSM) -> None:
        if state == PositionFSM.EMPTY:
            self.__short_fsm = state
        else:
            self.__short_fsm &= ~(PositionFSM.EMPTY)
            self.__short_fsm |= state

        if self.__short_fsm & self.__all_states == self.__all_states:
            self.__short_fsm = PositionFSM.EMPTY

    def position_state(self, state: PositionFSM, is_long: bool) -> bool:
        return bool(self.long & state) if is_long else bool(self.short & state)

    def is_averaging(self, order_param: int) -> bool:
        is_long: bool = bool(order_param & c.OF_LONG)
        is_buy: bool = bool(order_param & c.OF_BUY)

        if (is_buy and is_long) or (not is_buy and not is_long):
            return not self.position_state(PositionFSM.EMPTY, is_long)
        else:
            return False
