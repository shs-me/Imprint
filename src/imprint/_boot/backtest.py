from copy import deepcopy
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import final, override

from loguru import logger

import imprint.configs as cfg
from imprint._boot.base import Base, InitFailed
from imprint._core.configs import (
    Account,
    Coin,
    MarketDataStream,
    Percent,
    Setup,
)
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

    _coins: list[Coin] = field(init=False)
    _accounts: list[Account] = field(init=False)

    @override
    def _post_init(self) -> None:
        self._coins = []
        self._accounts = []

        self._segments.append(
            MarketDataStream(
                data_size=32,
                cast_to_int64=True,
                count_reader=2 if self.with_execution else 1,
            )
        )

        self.prepare_coin_config()
        self._other_configs.append(self._coins)

        self.prepare_account_config()
        self._other_configs.append(self._accounts)

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

    @override
    def prepare_setup_config(self) -> None:
        _ = self.run_mode
        # - - -
        Base.prepare_setup_config(self)

        start_dates: list[str] = self.to_list(_.backtest_start_date)
        end_dates: list[str] = self.to_list(_.backtest_end_date)

        for idx, (st, ed) in enumerate(
            zip_longest(start_dates, end_dates, fillvalue=None)
        ):
            setup: Setup | None = self.list_get(self._setups, idx)
            if not setup:
                setup = deepcopy(self._setups[-1])
                self._setups.append(setup)

            if isinstance(st, str):
                setup.backtest_start_date = st
            if isinstance(ed, str):
                setup.backtest_end_date = ed

    def prepare_coin_config(self) -> None:
        _ = self.run_mode
        # - - -
        symbols = self.to_list(_.symbols)
        tick_sizes = self.to_list(_.tick_size)
        lot_sizes = self.to_list(_.lot_size)

        for sym, ts, ls in zip_longest(
            symbols, tick_sizes, lot_sizes, fillvalue=None
        ):
            coin: Coin = deepcopy(self._coins[-1]) if self._coins else Coin()
            self._coins.append(coin)

            if isinstance(sym, str):
                coin.symbol = sym
            if isinstance(ts, str):
                coin.tick_size = ts
            if isinstance(ls, str):
                coin.lot_size = ls

    def prepare_account_config(self) -> None:
        _ = self.run_mode.account
        # - - -
        balances = self.to_list(_.balance)
        leverages = self.to_list(_.leverage)
        min_order_size = self.to_list(_.min_order_size)
        maker_commissions = self.to_list(_.maker_commission)
        taker_commissions = self.to_list(_.taker_commission)
        active_order_limits = self.to_list(_.active_order_limit)
        scale_precs = self.to_list(_.scale_prec)
        latency_ms = self.to_list(_.latency_ms)
        slippage = self.to_list(_.slippage)

        for b, lev, mos, mc, tc, aol, scp, lm, slp in zip_longest(
            balances,
            leverages,
            min_order_size,
            maker_commissions,
            taker_commissions,
            active_order_limits,
            scale_precs,
            latency_ms,
            slippage,
            fillvalue=None,
        ):
            account = (
                deepcopy(self._accounts[-1]) if self._accounts else Account()
            )
            self._accounts.append(account)

            if isinstance(b, float):
                account.balance = b
            if isinstance(lev, int):
                account.leverage = lev
            if isinstance(mos, float):
                account.min_order_size = mos
            if isinstance(mc, Percent):
                account.maker_commission = mc
            if isinstance(tc, Percent):
                account.taker_commission = tc
            if isinstance(aol, int):
                account.active_order_limit = aol
            if isinstance(scp, int):
                account.scale_prec = scp
            if isinstance(lm, int):
                account.latency_ms = lm
            if isinstance(slp, Percent):
                account.slippage = slp

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
            c, s, a = self._coins[-1], self._setups[-1], self._accounts[-1]

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
