from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import final, override

from loguru import logger

from imprint._boot.base import Base, BoundFactory, EngineNotBuilded, InitFailed
from imprint._boot.configs import (
    AccountBatch,
    FootprintBatch,
    RiskManagementBatch,
)
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
from imprint._core.footprint import StrategyEngine
from imprint._core.pipeline.executing import ExecutionEngine
from imprint._core.utils import DownloadAggTradesHistory
from imprint._core.utils.agg_trades_history_downloader import DownloadError
from imprint._core.utils.exc_dumper import error_handler
from imprint._vis.main import Render


@dataclass(slots=True)
class Backtest(Base):
    _symbol: list[str]
    _tick_size: list[str]
    _lot_size: list[str]
    _start_date: list[str]
    _end_date: list[str]
    _account: AccountBatch

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
                count_reader=2 if self._with_execution else 1,
            )
        )

        self._prepare_coin_config()
        self._other_configs.append(self._coins)

        self._prepare_account_config()
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
    def _prepare_setup_config(self) -> None:
        Base._prepare_setup_config(self)

        for idx, (st, ed) in enumerate(
            zip_longest(self._start_date, self._end_date, fillvalue=None)
        ):
            setup: Setup | None = self._list_get(self._setups, idx)
            if not setup:
                setup = deepcopy(self._setups[-1])
                self._setups.append(setup)

            if isinstance(st, str):
                setup.backtest_start_date = st
            if isinstance(ed, str):
                setup.backtest_end_date = ed

    def _prepare_coin_config(self) -> None:
        for sym, ts, ls in zip_longest(
            self._symbol, self._tick_size, self._lot_size, fillvalue=None
        ):
            coin: Coin = deepcopy(self._coins[-1]) if self._coins else Coin()
            self._coins.append(coin)

            if isinstance(sym, str):
                coin.symbol = sym
            if isinstance(ts, str):
                coin.tick_size = ts
            if isinstance(ls, str):
                coin.lot_size = ls

    def _prepare_account_config(self) -> None:
        _ = self._account
        # - - -
        for b, lev, mos, mc, tc, aol, scp, lm, slp in zip_longest(
            _.balance,
            _.leverage,
            _.min_order_size,
            _.maker_commission,
            _.taker_commission,
            _.active_order_limit,
            _.scale_prec,
            _.latency_ms,
            _.slippage,
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
        if self._init_complete and self._with_execution:
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


@final
@dataclass(slots=True)
class BacktestBuilder:
    symbols: list[str]
    start_date: list[str]
    end_date: list[str]
    tick_size: list[str]
    lot_size: list[str]
    with_execution: bool

    _account: AccountBatch = field(
        default_factory=lambda: AccountBatch(), init=False
    )
    _footprint: FootprintBatch = field(
        default_factory=lambda: FootprintBatch(), init=False
    )
    _risk_management: RiskManagementBatch = field(
        default_factory=lambda: RiskManagementBatch(), init=False
    )
    _algorithm: list[type[StrategyEngine]] = field(init=False)
    _execution: list[type[ExecutionEngine]] = field(init=False)
    _engine: BacktestEngine | None = field(default=None, init=False)

    @property
    def account(self) -> type[AccountBatch]:
        return BoundFactory(AccountBatch, self, "_account")  # pyright: ignore[ reportReturnType]

    @property
    def footprint(self) -> type[FootprintBatch]:
        return BoundFactory(FootprintBatch, self, "_footprint")  # pyright: ignore[ reportReturnType]

    @property
    def risk_management(self) -> type[RiskManagementBatch]:
        return BoundFactory(RiskManagementBatch, self, "_risk_management")  # pyright: ignore[ reportReturnType]

    def strategy(
        self,
        algorithm: list[type[StrategyEngine]],
        execution: list[type[ExecutionEngine]],
    ) -> BacktestBuilder:
        self._algorithm = algorithm
        self._execution = execution
        return self

    def build(self) -> None:
        if self._engine is None:
            self._engine = BacktestEngine(
                _algorithm=self._algorithm,
                _execution=self._execution,
                _footprint=self._footprint,
                _risk_management=self._risk_management,
                _with_execution=self.with_execution,
                _symbol=self.symbols,
                _tick_size=self.tick_size,
                _lot_size=self.lot_size,
                _start_date=self.start_date,
                _end_date=self.end_date,
                _account=self._account,
            )

    @property
    def engine(self) -> BacktestEngine:
        if self._engine is not None:
            return self._engine
        else:
            raise EngineNotBuilded
