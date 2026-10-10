"""Provide backtest engine orchestration, historical data downloading, and builder interfaces."""

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
from imprint._core import constant as c
from imprint._core.configs import (
    Account,
    Coin,
    MarketDataStream,
    Percent,
    Setup,
)
from imprint._core.footprint import StrategyEngine
from imprint._core.pipeline.executing import ExecutionEngine
from imprint._core.utils import DownloadAggTradesHistory
from imprint._core.utils.agg_trades_history_downloader import DownloadError
from imprint._core.utils.exc_dumper import error_handler


@dataclass(slots=True)
class Backtest(Base):
    """Manage backtest simulation setup, historical trade downloads, and visualization serving.

    Parameters
    ----------
    _symbol : list[str]
        Sequence of trading symbols for backtesting.
    _tick_size : list[str]
        Sequence of asset price tick sizes.
    _lot_size : list[str]
        Sequence of asset order quantity lot sizes.
    _start_date : list[str]
        Sequence of backtest start date strings in ``YYYY-MM-DD`` format.
    _end_date : list[str]
        Sequence of backtest end date strings in ``YYYY-MM-DD`` format.
    _account : AccountBatch
        Account batch configuration parameters.

    Attributes
    ----------
    _coins : list[Coin]
        Compiled sequence of coin configurations.
    _accounts : list[Account]
        Compiled sequence of account simulation configurations.
    """

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
        """Initialize shared memory, prepare coin/account configurations, and download historical trade data."""
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
        """Construct setup configurations with historical start and end date boundaries."""
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
        """Construct coin metadata configurations for target backtest symbols."""
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
        """Construct account state configurations from account batch parameter sequences."""
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
    def run_vis(
        self, auto_open: bool = False, port_file: str = "streamlit.port"
    ) -> None:
        """Launch and manage the Streamlit visualization dashboard process in the background.

        Parameters
        ----------
        auto_open : bool, default=False
            Whether to automatically open the Streamlit URL in the default web browser.
        port_file : str, default="streamlit.port"
            Filename for storing the port under the run directory.
        """
        if self._init_complete and self._with_execution:
            import os
            import socket
            import subprocess
            import webbrowser

            os.makedirs(c.RUNS_DIR, exist_ok=True)
            port_file = f"{c.RUNS_DIR}/{port_file}"

            def is_port_in_use(p: int) -> bool:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    return s.connect_ex(("127.0.0.1", p)) == 0

            if os.path.exists(port_file):
                with open(port_file, "r") as f:
                    port: int = int(f.read().strip())

                server_running: bool = is_port_in_use(port)
                if server_running:
                    if auto_open:
                        webbrowser.open(f"http://localhost:{port}")

                    return logger.info("Streamlit server is already running.")

            import sys

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]

            cmd: list[str] = [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "src/imprint/_vis/main.py",
                "--server.headless=true",
                f"--server.port={port}",
            ]

            process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

            import time

            for _ in range(20):
                if is_port_in_use(port):
                    break

                time.sleep(0.2)

            with open(port_file, "w") as f:
                f.write(str(port))

            webbrowser.open(f"http://localhost:{port}")
            logger.info(
                f"Streamlit server started in background (PID: {process.pid}, port: {port})."
            )


@final
@dataclass(slots=True)
class BacktestEngine(Backtest):  # pyright: ignore[reportUninitializedInstanceVariable]
    """Concrete backtest execution engine instance."""


@final
@dataclass(slots=True)
class BacktestBuilder:
    """Fluent builder for configuring and instantiating multi-symbol backtest engines.

    Parameters
    ----------
    symbols : list[str]
        List of target trading symbols.
    start_date : list[str]
        List of backtest start dates in ``YYYY-MM-DD`` format.
    end_date : list[str]
        List of backtest end dates in ``YYYY-MM-DD`` format.
    tick_size : list[str]
        List of asset price tick sizes.
    lot_size : list[str]
        List of asset order quantity lot sizes.
    with_execution : bool
        Whether to enable simulated order execution.

    Attributes
    ----------
    _account : AccountBatch
        Configured account parameter batch.
    _footprint : FootprintBatch
        Configured footprint parameter batch.
    _risk_management : RiskManagementBatch
        Configured risk management parameter batch.
    _algorithm : list[type[StrategyEngine]]
        Configured strategy algorithm classes.
    _execution : list[type[ExecutionEngine]]
        Configured execution engine classes.
    _engine : BacktestEngine | None
        Instantiated backtest engine, or None if not yet built.
    """

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
        """Bind and configure account parameters for backtesting.

        Returns
        -------
        BoundFactory
            Factory interface for setting account batch attributes.
        """
        return BoundFactory(AccountBatch, self, "_account")  # pyright: ignore[ reportReturnType]

    @property
    def footprint(self) -> type[FootprintBatch]:
        """Bind and configure footprint chart aggregation parameters.

        Returns
        -------
        BoundFactory
            Factory interface for setting footprint batch attributes.
        """
        return BoundFactory(FootprintBatch, self, "_footprint")  # pyright: ignore[ reportReturnType]

    @property
    def risk_management(self) -> type[RiskManagementBatch]:
        """Bind and configure risk management and execution timeout parameters.

        Returns
        -------
        BoundFactory
            Factory interface for setting risk management batch attributes.
        """
        return BoundFactory(RiskManagementBatch, self, "_risk_management")  # pyright: ignore[ reportReturnType]

    def strategy(
        self,
        algorithm: list[type[StrategyEngine]],
        execution: list[type[ExecutionEngine]],
    ) -> BacktestBuilder:
        """Assign strategy algorithms and execution engines to the backtest builder.

        Parameters
        ----------
        algorithm : list[type[StrategyEngine]]
            Sequence of strategy engine algorithm classes.
        execution : list[type[ExecutionEngine]]
            Sequence of execution engine classes.

        Returns
        -------
        BacktestBuilder
            The builder instance for method chaining.
        """
        self._algorithm = algorithm
        self._execution = execution
        return self

    def build(self) -> None:
        """Construct and initialize the backtest engine instance from accumulated configurations.

        Raises
        ------
        InitFailed
            If historical data download or configuration validation fails.
        """
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
        """Retrieve the built backtest engine instance.

        Returns
        -------
        BacktestEngine
            Configured backtest engine instance.

        Raises
        ------
        EngineNotBuilded
            If build() has not been called prior to accessing the engine.
        """
        if self._engine is not None:
            return self._engine
        else:
            raise EngineNotBuilded
