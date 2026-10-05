"""Position state tracking and averaging evaluation manager."""

from dataclasses import dataclass, field

from imprint._core import constant as c
from imprint._core.account.risk_management import RiskManagement
from imprint._core.settings import PositionFSM


@dataclass(slots=True)
class Manager(RiskManagement):
    """Account manager combining balance properties, risk management, and position FSM tracking.

    Aggregates account configuration, risk/sizing logic, and active position lifecycle
    tracking via bitmask finite state machines.

    Attributes
    ----------
    long : PositionFSM
        Current state bitmask flags for long positions.
    short : PositionFSM
        Current state bitmask flags for short positions.
    """

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
        """Get active state flags for long positions.

        Returns
        -------
        PositionFSM
            Bitmask flag representing current long position state.
        """
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
        """Get active state flags for short positions.

        Returns
        -------
        PositionFSM
            Bitmask flag representing current short position state.
        """
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
        """Check if position for specified side contains given state flag.

        Parameters
        ----------
        state : PositionFSM
            Target position state bitmask flag to check.
        is_long : bool
            True to inspect long position state, False for short position state.

        Returns
        -------
        bool
            True if target state bit is set for specified position side, False otherwise.
        """
        return bool(self.long & state) if is_long else bool(self.short & state)

    def is_averaging(self, order_param: int) -> bool:
        """Determine whether an order constitutes position scale-in (averaging).

        Parameters
        ----------
        order_param : int
            Bitmask containing order side (`c.OF_LONG`) and direction (`c.OF_BUY`).

        Returns
        -------
        bool
            True if order increases an existing position size, False otherwise.
        """
        is_long: bool = bool(order_param & c.OF_LONG)
        is_buy: bool = bool(order_param & c.OF_BUY)

        if (is_buy and is_long) or (not is_buy and not is_long):
            return not self.position_state(PositionFSM.EMPTY, is_long)
        else:
            return False
