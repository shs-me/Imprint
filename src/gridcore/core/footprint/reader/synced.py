from abc import ABC, abstractmethod

import numpy as np
from numpy import int64
from numpy.typing import NDArray

from ... import constant as c
from ...ipc import NodeManager
from .base import Base
from .sync import Sync


class Synced(Base, ABC):
    def __init__(
        self,
        manager: NodeManager,
        sync: Sync,
        find_patterns_in_update_bar: bool = False,
        find_patterns_in_update_closed_bar: bool = False,
        find_patterns_in_update_clusters: bool = False,
    ) -> None:
        Base.__init__(self, manager=manager)

        self._sync: Sync = sync
        self._fpiu_bar: bool = find_patterns_in_update_bar
        self._fpiu_closed_bar: bool = find_patterns_in_update_closed_bar
        self._fpiu_clusters: bool = find_patterns_in_update_clusters

    def _init_array(self) -> None:
        Base._init_array(self)
        self.algorithm_metadata: NDArray[int64] = np.zeros((2, 2), dtype=int64)
        self.amRow: int = 0

    def _update_clusters(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None:
        Base._update_clusters(self, idYmin, idYmax, idXmin, idXmax)
        if self._fpiu_clusters:
            self.find_patterns_in_update_clusters(idYmin, idYmax, idXmin, idXmax)

    def _update_bar(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        Base._update_bar(self, idYmin, idYmax, idxBid, idxAsk)
        if self._fpiu_bar:
            self.find_patterns_in_update_bar(idYmin, idYmax, idxBid, idxAsk)

    def _update_closed_bar_and_fp(self) -> None:
        Base._update_closed_bar_and_fp(self)
        if self._fpiu_closed_bar:
            self.find_patterns_in_update_closed_bar()

    @abstractmethod
    def find_patterns_in_update_clusters(
        self, idYmin: int64, idYmax: int64, idXmin: int64, idXmax: int64
    ) -> None:
        pass

    @abstractmethod
    def find_patterns_in_update_closed_bar(self) -> None:
        pass

    @abstractmethod
    def find_patterns_in_update_bar(
        self, idYmin: int64, idYmax: int64, idxBid: int, idxAsk: int
    ) -> None:
        pass

    def _final_actions(self) -> None:
        if self._manager.cfgFootprint.save_algorithm_metadata:
            np.save(
                c.ALGORITHM_METADATA_DUMP_PATH, self.algorithm_metadata[: self.amRow, :]
            )

    def send_signal(
        self,
        is_market: bool,
        is_long: bool,
        is_buy: bool,
        idy: int64,
        idx: int | None = None,
        pass_lag: bool = True,
    ) -> int | None:
        nPrice = int(self.con.to_nPrice(idy))
        idx = idx if (idx is not None) else self.last_idx
        timestamp = int(self.fp.bar[idx].ind.time.last_trade)
        return self._sync.send_signal(
            nPrice=nPrice,
            timestamp=timestamp,
            is_long=is_long,
            is_buy=is_buy,
            is_market=is_market,
            pass_lag=pass_lag,
        )
