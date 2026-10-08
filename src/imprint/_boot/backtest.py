from copy import deepcopy
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import final, override

from loguru import logger

import imprint.configs as cfg
from imprint._boot.base import Base, InitFailed
from imprint._core.configs import Account, Coin, Setup
from imprint._core.configs import MarketDataStream as _MDS
from imprint._core.constant import (
    EQUITY_HISTORY_DATA_PATH,
    FOOTPRINT_HEADERS_DATA_PATH,
    ORDERS_HISTORY_DATA_PATH,
)
from imprint._core.utils import DownloadAggTradesHistory
from imprint._core.utils.agg_trades_history_downloader import DownloadError
from imprint._core.utils.exc_dumper import error_handler
from imprint._vis.main import Render


@dataclass(slots=True)
class Backtest(Base):
    """Manage historical backtesting initialization, data downloading, and visualization rendering.

    Parameters
    ----------
    run_mode : imprint.configs.Backtest
        Backtest configuration parameters including start/end dates, tick size, lot size, and account settings.

    Attributes
    ----------
    run_mode : imprint.configs.Backtest
        Backtest configuration parameters.
    """

    run_mode: cfg.Backtest

    _account: list[Account] = field(init=False)

    @override
    def _post_init(self) -> None:
        """Download historical aggregated trades data and initialize backtest market data stream and coin parameters.

        Returns
        -------
        bool
            True if historical data download and initialization succeed; False if DownloadError occurs.

        Raises
        ------
        DownloadError
            Caught internally if historical market data retrieval fails from remote repositories.
        """
        self._segments.append(
            _MDS(
                data_size=32,
                cast_to_int64=True,
                count_reader=2 if self.with_execution else 1,
            )
        )

        self._account = self.to_list(self.run_mode.account, Account())
        self._other_configs.append(self._account)

        tick_sizes: list[str] = self.to_list(self.run_mode.tick_size, "")
        lot_sizes: list[str] = self.to_list(self.run_mode.lot_size, "")
        start_dates: list[str] = self.to_list(
            self.run_mode.backtest_start_date, ""
        )
        end_dates: list[str] = self.to_list(self.run_mode.backtest_end_date, "")

        coin_idx, setup_idx = 0, 0
        for ts, ls, sd, ed in zip_longest(
            tick_sizes, lot_sizes, start_dates, end_dates, fillvalue=None
        ):
            if ts or ls:
                coin: Coin | None = self.list_get(self._coins, coin_idx)
                if not coin:
                    coin = deepcopy(self._coins[-1])
                    self._coins.append(coin)
                else:
                    coin_idx += 1

                if ts:
                    coin.tick_size = ts
                if ls:
                    coin.lot_size = ls

            if sd or ed:
                setup: Setup | None = self.list_get(self._setups, setup_idx)
                if not setup:
                    setup = deepcopy(self._setups[-1])
                    self._setups.append(setup)
                else:
                    setup_idx += 1

                if sd:
                    setup.backtest_start_date = sd
                if ed:
                    setup.backtest_end_date = ed

        try:
            downloader: DownloadAggTradesHistory = DownloadAggTradesHistory(
                logger=logger
            )
            for coin, setup in zip_longest(
                self._coins, self._setups, fillvalue=None
            ):
                if not coin:
                    coin = self._coins[-1]
                if not setup:
                    setup = self._setups[-1]

                downloader.download(
                    symbol=coin.symbol,
                    start_date_str=setup.backtest_start_date,
                    end_date_str=setup.backtest_end_date,
                    price_mult=coin.price_mult,
                    qty_mult=coin.qty_mult,
                )
        except DownloadError as e:
            raise InitFailed(f"Download agg trades data, failed: {e}") from e

    def list_get[T](self, arr: list[T], index: int) -> T | None:
        try:
            return arr[index]
        except IndexError:
            return None

    @error_handler()
    def run_vis(self, auto_open: bool = True) -> None:
        """Render interactive HTML charts and analytical visualizations from backtest simulation outputs.

        Parameters
        ----------
        auto_open : bool, default=True
            Whether to automatically open the generated visualization HTML file in the default web browser.
        """
        if self._init_complete and self.with_execution:
            logger.info("Visualization, started.")
            c, s, a = self._coins[-1], self._setups[-1], self._account[-1]

            Render(
                footprint_headers_path=FOOTPRINT_HEADERS_DATA_PATH,
                symbol=c.symbol,
                start_date_str=s.backtest_start_date,
                end_date_str=s.backtest_end_date,
                equity_history_path=EQUITY_HISTORY_DATA_PATH,
                orders_history_path=ORDERS_HISTORY_DATA_PATH,
                start_balance=a.balance,
                price_mult=c.price_mult,
                qty_mult=c.qty_mult,
                scale_mult=a.scale_mult,
                leverage=a.leverage,
                timeframe=self._footprints[-1].timeframe,
                auto_open=auto_open,
            )
            logger.info("Visualization, closed.\n")


@final
@dataclass(slots=True)
class BacktestEngine(Backtest):  # pyright: ignore[reportUninitializedInstanceVariable]
    """Concrete backtest execution engine instance."""
